import json, datetime, hashlib, re, csv, io, uuid, calendar, logging
from flask import Blueprint, request, jsonify, abort
from database import get_db, current_user, add_notif, require_role, log_audit
from llm import call_llm, SYSTEM_IMPORT
from security_utils import decrypt_patient, decrypt_field, encrypt_patient_fields, sanitize

logger = logging.getLogger(__name__)

bp = Blueprint('patients', __name__)


def _assert_owns_patient(db, u, pid):
    """Abort 403 if a médecin does not own the patient. Admins pass freely."""
    if u['role'] == 'admin':
        return
    if u['role'] == 'medecin':
        row = db.execute(
            "SELECT id FROM patients WHERE id=? AND medecin_id=?", (pid, u['id'])
        ).fetchone()
        if not row:
            abort(403)
    # patients are checked separately at the route level (patient_id match)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _build_patient(db, pid, strip_images=True):
    """Assemble a full patient dict from all DB tables (PII decrypted)."""
    row = db.execute("SELECT * FROM patients WHERE id = ?", (pid,)).fetchone()
    if not row:
        return None
    p = decrypt_patient(dict(row))
    p['antecedents'] = json.loads(p['antecedents'] or '[]')
    p['allergies']   = json.loads(p['allergies']   or '[]')

    p['historique'] = [dict(r) for r in
        db.execute("SELECT * FROM historique WHERE patient_id=? ORDER BY date DESC", (pid,))]

    rdvs = [dict(r) for r in
        db.execute("SELECT * FROM rdv WHERE patient_id=? ORDER BY date, heure", (pid,))]
    for r in rdvs:
        r['urgent'] = bool(r['urgent'])
    p['rdv'] = rdvs

    imgs = [dict(r) for r in
        db.execute("SELECT * FROM documents WHERE patient_id=? AND source='imagerie' AND deleted=0", (pid,))]
    docs = [dict(r) for r in
        db.execute("SELECT * FROM documents WHERE patient_id=? AND source='document' AND deleted=0", (pid,))]
    for item in imgs + docs:
        item['has_image'] = bool(item.get('image_b64'))
    if strip_images:
        for item in imgs + docs:
            item.pop('image_b64', None)
    p['imagerie']  = imgs
    p['documents'] = docs

    questions = [dict(r) for r in
        db.execute("SELECT * FROM questions WHERE patient_id=? AND deleted=0 ORDER BY date DESC", (pid,))]
    for q in questions:
        q['reponse_validee'] = bool(q['reponse_validee'])
    p['questions'] = questions

    p['ivt'] = [dict(r) for r in
        db.execute("SELECT * FROM ivt WHERE patient_id=? ORDER BY date DESC, numero DESC", (pid,))]

    ordonnances = [dict(r) for r in
        db.execute("SELECT * FROM ordonnances WHERE patient_id=? ORDER BY date DESC", (pid,))]
    for o in ordonnances:
        try:
            o['contenu'] = json.loads(o['contenu'] or '{}')
        except Exception:
            o['contenu'] = {}
    p['ordonnances'] = ordonnances

    return p


def _anonymize(p):
    return {
        "id":          p["id"],
        "code":        hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe":        p["sexe"],
        "age":         datetime.datetime.now().year - int(p["ddn"][:4]) if p.get("ddn") else 0,
        "antecedents": p["antecedents"],
        "nb_rdv":      len(p["rdv"]),
        "nb_imagerie": len(p["imagerie"])
    }


def _add_months(d, months):
    """Add a number of months to a date, clamping to end-of-month."""
    month = d.month - 1 + months
    year  = d.year + month // 12
    month = month % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


SUIVI_ETAPES = [
    ("J7",     lambda d: d + datetime.timedelta(days=7)),
    ("J30",    lambda d: d + datetime.timedelta(days=30)),
    ("J2Mois", lambda d: _add_months(d, 2)),
    ("J3Mois", lambda d: _add_months(d, 3)),
    ("J6Mois", lambda d: _add_months(d, 6)),
    ("J12M",   lambda d: _add_months(d, 12)),
    ("J18Mois",lambda d: _add_months(d, 18)),
    ("A2",     lambda d: _add_months(d, 24)),
]


def _generate_suivi(db, pid, date_chirurgie_str, medecin_nom='', type_chirurgie=''):
    """Create the 8 post-op follow-up steps and their confirmed RDVs. Skips existing ones."""
    try:
        base = datetime.date.fromisoformat(date_chirurgie_str)
    except ValueError:
        return
    existing = {r['etape'] for r in
                db.execute("SELECT etape FROM suivi_postop WHERE patient_id=?", (pid,)).fetchall()}
    for etape, calc in SUIVI_ETAPES:
        if etape in existing:
            continue
        sid         = "S" + str(uuid.uuid4())[:7].upper()
        rdv_id      = "RDV" + str(uuid.uuid4())[:6].upper()
        date_prevue = calc(base).isoformat()
        type_rdv    = f"Suivi post-op {etape}"
        notes_rdv   = f"Suivi post-opératoire {etape} — {type_chirurgie or 'chirurgie'}"
        # Confirmed RDV in the agenda
        db.execute(
            "INSERT INTO rdv (id, patient_id, date, heure, type, statut, medecin, notes, urgent, demande_par) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rdv_id, pid, date_prevue, '09:00', type_rdv, 'confirmé', medecin_nom, notes_rdv, 0, 'system')
        )
        db.execute(
            "INSERT INTO suivi_postop (id, patient_id, etape, date_prevue, statut, rdv_id) VALUES (?,?,?,?,?,?)",
            (sid, pid, etape, date_prevue, 'a_faire', rdv_id)
        )
    db.commit()


def _auto_create_account(db, pid, nom, prenom, email='', app_host=''):
    """Auto-create a user account for a patient and email credentials if possible.

    Returns dict with username/password/email_sent, or None if account already exists.
    """
    from werkzeug.security import generate_password_hash as _hash

    if db.execute("SELECT id FROM users WHERE patient_id=?", (pid,)).fetchone():
        return None  # already has an account

    # Build a clean username from prenom.nom
    base = re.sub(r'[^a-z0-9._-]', '',
                  f"patient.{prenom.lower().strip()}.{nom.lower().strip()}")
    if not base or base == 'patient..':
        base = f"patient.{pid.lower()}"
    username = base
    counter  = 1
    while db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        username = f"{base}{counter}"
        counter += 1

    # Random 12-char alphanumeric password
    import secrets as _sec, string as _str
    alphabet = _str.ascii_letters + _str.digits
    password = ''.join(_sec.choice(alphabet) for _ in range(12))

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id, status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (uid, username, _hash(password), 'patient', nom, prenom, pid, 'active')
    )

    email_sent = False
    if email and '@' in email:
        try:
            from email_notif import send_credentials_email
            email_sent = send_credentials_email(email, prenom, nom, username, password, app_host)
        except Exception:
            pass

    return {"username": username, "password": password, "email_sent": email_sent}


def _next_patient_id(db):
    row = db.execute(
        "SELECT MAX(CAST(SUBSTR(id,2) AS INTEGER)) FROM patients WHERE id GLOB 'P[0-9]*'"
    ).fetchone()
    n = (row[0] or 0) + 1
    return f"P{n:03d}"


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@bp.route('/api/patients', methods=['GET'])
def get_patients():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()
    q = request.args.get('q', '').lower()

    if u['role'] == 'patient':
        pid = u.get('patient_id')
        row = db.execute("SELECT id, nom, prenom FROM patients WHERE id=?", (pid,)).fetchone()
        if row:
            return jsonify([decrypt_patient(dict(row))])
        return jsonify([])

    # médecin — ses propres patients avec recherche optionnelle (single JOIN, no N+1)
    mid = u['id'] if u['role'] == 'medecin' else None
    query = """
        SELECT p.*,
               COUNT(CASE WHEN r.urgent=1 AND r.statut='en_attente' THEN 1 END) AS nb_rdv_urgent
        FROM patients p
        LEFT JOIN rdv r ON r.patient_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY p.nom, p.prenom
    """
    if mid:
        rows = db.execute(query.format(where="WHERE p.medecin_id = ?"), (mid,)).fetchall()
    else:
        rows = db.execute(query.format(where=""), ()).fetchall()

    result = []
    for row in rows:
        p = decrypt_patient(dict(row))
        p['antecedents'] = json.loads(p['antecedents'] or '[]')
        if q and not (q in p['nom'].lower() or q in p['prenom'].lower() or q in p['id'].lower()):
            continue
        result.append({
            "id": p['id'], "nom": p['nom'], "prenom": p['prenom'],
            "ddn": p['ddn'], "antecedents": p['antecedents'][:2],
            "nb_rdv_urgent": p['nb_rdv_urgent'],
            "medecin_id": p.get('medecin_id', '')
        })
    return jsonify(result)


@bp.route('/api/patients/<pid>', methods=['GET'])
def get_patient(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    # Enforce medecin ownership — a médecin can only access their own patients
    if u['role'] in ('medecin',):
        _assert_owns_patient(db, u, pid)
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404

    if u['role'] == 'patient':
        patient_view = dict(p)
        patient_view['historique'] = [
            {
                "date":      h["date"],
                "motif":     h["motif"],
                "traitement": h["traitement"],
                "acuite_od": h.get("acuite_od", ""),
                "acuite_og": h.get("acuite_og", "")
            }
            for h in p["historique"]
        ]
        return jsonify(patient_view)

    return jsonify(p)


@bp.route('/api/patients', methods=['POST'])
@require_role('medecin', 'admin')
def add_patient():
    u = current_user()
    data = request.json or {}
    db = get_db()
    pid = _next_patient_id(db)
    medecin_id = data.get("medecin_id") or (u['id'] if u['role'] == 'medecin' else '')
    send_email = data.get("send_email", True)
    # Encrypt PII before persisting
    pii = encrypt_patient_fields({
        "nom":       sanitize(data.get("nom", ""),       max_len=100),
        "prenom":    sanitize(data.get("prenom", ""),    max_len=100),
        "ddn":       sanitize(data.get("ddn", ""),       max_len=20),
        "telephone": sanitize(data.get("telephone", ""), max_len=30),
        "email":     sanitize(data.get("email", ""),     max_len=200),
    })
    try:
        db.execute(
            "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid,
             pii["nom"], pii["prenom"], pii["ddn"], sanitize(data.get("sexe",""), max_len=10),
             pii["telephone"], pii["email"],
             json.dumps(data.get("antecedents",[])), json.dumps(data.get("allergies",[])),
             medecin_id)
        )
        host  = request.host_url.rstrip('/')
        email = data.get("email","") if send_email else ''
        creds = _auto_create_account(
            db, pid,
            nom=data.get("nom",""), prenom=data.get("prenom",""),
            email=email, app_host=host
        )
        log_audit(db, 'INSERT', 'patients', pid, u['id'], pid,
                  f"{data.get('prenom','')} {data.get('nom','')}")
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"add_patient failed: {e}")
        return jsonify({"error": "Erreur lors de la création du patient"}), 500
    add_notif(db, "patient_added",
              f"Nouveau patient ajouté : {data.get('prenom','')} {data.get('nom','')}",
              u['role'], pid)
    return jsonify({"ok": True, "id": pid, "credentials": creds}), 201


@bp.route('/api/patients/<pid>', methods=['DELETE'])
@require_role('medecin', 'admin')
def delete_patient(pid):
    u = current_user()
    db = get_db()
    _assert_owns_patient(db, u, pid)
    patient = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not patient:
        return jsonify({"error": "Non trouvé"}), 404
    db.execute("DELETE FROM historique WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM rdv WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM suivi_postop WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM documents WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM questions WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM ordonnances WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM ivt WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM notifications WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM users WHERE patient_id=?", (pid,))
    db.execute("DELETE FROM patients WHERE id=?", (pid,))
    log_audit(db, 'DELETE', 'patients', pid, u['id'], pid,
              f"{patient['prenom']} {patient['nom']}")
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>', methods=['PUT'])
def update_patient(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _assert_owns_patient(db, u, pid)
    if not db.execute("SELECT id FROM patients WHERE id=?", (pid,)).fetchone():
        return jsonify({"error": "Non trouvé"}), 404
    data = request.json or {}
    pii = encrypt_patient_fields({
        "nom":       sanitize(data.get("nom", ""),       max_len=100),
        "prenom":    sanitize(data.get("prenom", ""),    max_len=100),
        "ddn":       sanitize(data.get("ddn", ""),       max_len=20),
        "telephone": sanitize(data.get("telephone", ""), max_len=30),
        "email":     sanitize(data.get("email", ""),     max_len=200),
    })
    db.execute(
        "UPDATE patients SET nom=?, prenom=?, ddn=?, sexe=?, telephone=?, email=?, "
        "antecedents=?, allergies=? WHERE id=?",
        (pii["nom"], pii["prenom"], pii["ddn"], sanitize(data.get("sexe",""), max_len=10),
         pii["telephone"], pii["email"],
         json.dumps(data.get("antecedents",[])), json.dumps(data.get("allergies",[])), pid)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/assigner', methods=['POST'])
def assigner_medecin(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    new_medecin_id = data.get('medecin_id', '').strip()
    if not new_medecin_id:
        return jsonify({"error": "medecin_id requis"}), 400
    db = get_db()
    _assert_owns_patient(db, u, pid)
    target = db.execute(
        "SELECT id FROM users WHERE id=? AND role='medecin'", (new_medecin_id,)
    ).fetchone()
    if not target:
        return jsonify({"error": "Médecin introuvable ou identifiant invalide"}), 404
    db.execute("UPDATE patients SET medecin_id=? WHERE id=?", (new_medecin_id, pid))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/chirurgie', methods=['POST'])
def set_chirurgie(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    db.execute(
        "UPDATE patients SET date_chirurgie=?, type_chirurgie=? WHERE id=?",
        (data.get('date_chirurgie',''), data.get('type_chirurgie',''), pid)
    )
    db.commit()
    date_chir   = data.get('date_chirurgie', '')
    type_chir   = data.get('type_chirurgie', '')
    medecin_nom = f"{u.get('prenom','')} {u.get('nom','')}".strip()
    if date_chir:
        _generate_suivi(db, pid, date_chir, medecin_nom=medecin_nom, type_chirurgie=type_chir)
    p = db.execute("SELECT prenom, nom FROM patients WHERE id=?", (pid,)).fetchone()
    if p:
        add_notif(db, "chirurgie",
                  f"✂️ Chirurgie planifiée pour {p['prenom']} {p['nom']} : {date_chir} — 8 RDV post-op créés",
                  "medecin", pid)
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/chirurgie', methods=['DELETE'])
def delete_chirurgie(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    # Delete all linked RDVs from the agenda
    rdv_ids = [r['rdv_id'] for r in
               db.execute("SELECT rdv_id FROM suivi_postop WHERE patient_id=? AND rdv_id!=''", (pid,)).fetchall()]
    for rid in rdv_ids:
        db.execute("DELETE FROM rdv WHERE id=?", (rid,))
    # Delete all suivi steps
    db.execute("DELETE FROM suivi_postop WHERE patient_id=?", (pid,))
    # Clear surgery fields on patient
    db.execute("UPDATE patients SET date_chirurgie='', type_chirurgie='' WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/export', methods=['GET'])
def export_patient(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _assert_owns_patient(db, u, pid)
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404
    anon = {
        "code":          hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe":          p["sexe"],
        "age":           datetime.datetime.now().year - int(p["ddn"][:4]) if p.get("ddn") else 0,
        "antecedents":   p["antecedents"],
        "allergies":     p["allergies"],
        "date_chirurgie": p.get("date_chirurgie",""),
        "type_chirurgie": p.get("type_chirurgie",""),
        "historique":    [{k: v for k, v in h.items() if k != 'medecin'} for h in p["historique"]],
        "nb_rdv":        len(p["rdv"]),
        "export_date":   datetime.datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(anon)


# ─── IMPORT ───────────────────────────────────────────────────────────────────

@bp.route('/api/import/csv', methods=['POST'])
def import_csv():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    csv_text = data.get('content', '')

    try:
        patients_raw = list(csv.DictReader(io.StringIO(csv_text)))
        prompt = (f"Voici des données CSV de patients:\n{csv_text[:3000]}\n\nNormalise et retourne le JSON."
                  if patients_raw
                  else f"Extrais les patients de ce texte:\n{csv_text[:3000]}")
    except Exception:
        prompt = f"Extrais les patients de ce texte:\n{csv_text[:3000]}"

    try:
        result_str = call_llm(prompt, SYSTEM_IMPORT, max_tokens=1500)
    except Exception as e:
        logger.error(f"LLM import failed: {e}")
        return jsonify({"ok": False, "error": "Service IA indisponible, réessayez dans quelques minutes."}), 503
    db = get_db()
    try:
        clean = re.sub(r'```(?:json)?|```', '', result_str).strip()
        patients_list = json.loads(clean)
        host  = request.host_url.rstrip('/')
        added = []
        for pd_data in patients_list:
            pid = _next_patient_id(db)
            nom    = sanitize(pd_data.get("nom",""),       max_len=100)
            prenom = sanitize(pd_data.get("prenom",""),    max_len=100)
            email  = sanitize(pd_data.get("email",""),     max_len=200)
            pii = encrypt_patient_fields({
                "nom": nom, "prenom": prenom,
                "ddn":       sanitize(pd_data.get("ddn",""),       max_len=20),
                "telephone": sanitize(pd_data.get("telephone",""), max_len=30),
                "email":     email,
            })
            db.execute(
                "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, pii["nom"], pii["prenom"], pii["ddn"],
                 pd_data.get("sexe",""), pii["telephone"], pii["email"],
                 json.dumps(pd_data.get("antecedents",[])), json.dumps(pd_data.get("allergies",[])),
                 u['id'])
            )
            creds = _auto_create_account(db, pid, nom=nom, prenom=prenom,
                                         email=email, app_host=host)
            added.append({
                "id": pid, "nom": nom, "prenom": prenom,
                "credentials": creds
            })
        db.commit()
        add_notif(db, "import", f"{len(added)} patient(s) importés depuis CSV", "medecin")
        return jsonify({"ok": True, "added": added, "count": len(added)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Impossible de parser: {e}", "raw": result_str[:500]})


@bp.route('/api/patients/<pid>/historique', methods=['POST'])
def add_historique(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    if not db.execute("SELECT id FROM patients WHERE id=?", (pid,)).fetchone():
        return jsonify({"error": "Patient non trouvé"}), 404
    hid = "H" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO historique (id,patient_id,date,motif,diagnostic,traitement,"
        "tension_od,tension_og,acuite_od,acuite_og,"
        "refraction_od_sph,refraction_od_cyl,refraction_od_axe,"
        "refraction_og_sph,refraction_og_cyl,refraction_og_axe,"
        "segment_ant,notes,medecin) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (hid, pid,
         data.get('date', datetime.date.today().isoformat()),
         data.get('motif',''), data.get('diagnostic',''), data.get('traitement',''),
         data.get('tension_od',''), data.get('tension_og',''),
         data.get('acuite_od',''), data.get('acuite_og',''),
         data.get('refraction_od_sph',''), data.get('refraction_od_cyl',''), data.get('refraction_od_axe',''),
         data.get('refraction_og_sph',''), data.get('refraction_og_cyl',''), data.get('refraction_og_axe',''),
         data.get('segment_ant',''), data.get('notes',''),
         u['nom'])
    )
    log_audit(db, 'INSERT', 'historique', hid, u['id'], pid,
              data.get('motif', ''))
    db.commit()
    return jsonify({"ok": True, "id": hid}), 201


@bp.route('/api/patients/<pid>/historique/<hid>', methods=['PUT'])
def update_historique(pid, hid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    if not db.execute("SELECT id FROM historique WHERE id=? AND patient_id=?", (hid, pid)).fetchone():
        return jsonify({"error": "Consultation non trouvée"}), 404
    db.execute(
        "UPDATE historique SET date=?,motif=?,diagnostic=?,traitement=?,"
        "tension_od=?,tension_og=?,acuite_od=?,acuite_og=?,"
        "refraction_od_sph=?,refraction_od_cyl=?,refraction_od_axe=?,"
        "refraction_og_sph=?,refraction_og_cyl=?,refraction_og_axe=?,"
        "segment_ant=?,notes=? WHERE id=? AND patient_id=?",
        (data.get('date',''), data.get('motif',''), data.get('diagnostic',''), data.get('traitement',''),
         data.get('tension_od',''), data.get('tension_og',''),
         data.get('acuite_od',''), data.get('acuite_og',''),
         data.get('refraction_od_sph',''), data.get('refraction_od_cyl',''), data.get('refraction_od_axe',''),
         data.get('refraction_og_sph',''), data.get('refraction_og_cyl',''), data.get('refraction_og_axe',''),
         data.get('segment_ant',''), data.get('notes',''),
         hid, pid)
    )
    log_audit(db, 'UPDATE', 'historique', hid, u['id'], pid,
              data.get('motif', ''))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/historique/<hid>', methods=['DELETE'])
def delete_historique(pid, hid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute("DELETE FROM historique WHERE id=? AND patient_id=?", (hid, pid))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/search', methods=['GET'])
def search_global():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    db  = get_db()
    ql  = f"%{q.lower()}%"
    results = []

    # Patients — search in decrypted PII (fetch scoped rows, decrypt in Python)
    scope_where = "WHERE p.medecin_id=?" if u['role'] == 'medecin' else ""
    scope_params = (u['id'],) if u['role'] == 'medecin' else ()
    pat_rows = db.execute(
        f"SELECT id, nom, prenom, ddn FROM patients p {scope_where}", scope_params
    ).fetchall()
    for r in pat_rows:
        dec = decrypt_patient(dict(r))
        nom_l    = (dec['nom']    or '').lower()
        prenom_l = (dec['prenom'] or '').lower()
        id_l     = (dec['id']     or '').lower()
        if q in nom_l or q in prenom_l or q in id_l:
            results.append({
                "type": "patient", "pid": dec["id"],
                "label": f"{dec['prenom']} {dec['nom']}",
                "sub":   f"Patient · {dec['ddn'] or '—'}"
            })

    # Consultations — motif, diagnostic, notes (non-encrypted fields)
    scope_join = "JOIN patients p ON h.patient_id=p.id" + (" WHERE p.medecin_id=?" if u['role'] == 'medecin' else "")
    scope_params2 = (u['id'],) if u['role'] == 'medecin' else ()
    hist_rows = db.execute(
        f"SELECT h.id, h.patient_id, h.date, h.motif, h.diagnostic, p.nom, p.prenom "
        f"FROM historique h {scope_join} "
        f"{'AND' if u['role'] == 'medecin' else 'WHERE'} "
        f"(lower(h.motif) LIKE ? OR lower(h.diagnostic) LIKE ? OR lower(h.notes) LIKE ?)",
        scope_params2 + (ql, ql, ql)
    ).fetchall()
    for r in hist_rows:
        dec = decrypt_patient({"nom": r["nom"], "prenom": r["prenom"]})
        results.append({
            "type": "consultation", "pid": r["patient_id"],
            "label": f"{r['motif'] or r['diagnostic'] or 'Consultation'}",
            "sub":   f"{dec['prenom']} {dec['nom']} · {r['date']}"
        })

    return jsonify(results[:12])


# ─── SUIVI POST-OP ────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/suivi', methods=['GET'])
def get_suivi(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM suivi_postop WHERE patient_id=? ORDER BY date_prevue", (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/suivi/<sid>', methods=['PUT'])
def update_suivi(pid, sid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM suivi_postop WHERE id=? AND patient_id=?", (sid, pid)).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404

    # Fields that can be updated
    statut        = data.get('statut',        row['statut'])
    date_reelle   = data.get('date_reelle',   row['date_reelle'])
    historique_id = data.get('historique_id', row['historique_id'])
    notes         = data.get('notes',         row['notes'])
    date_prevue   = data.get('date_prevue',   row['date_prevue'])
    heure         = data.get('heure',         None)

    db.execute(
        "UPDATE suivi_postop SET statut=?, date_reelle=?, historique_id=?, notes=?, date_prevue=? WHERE id=?",
        (statut, date_reelle, historique_id, notes, date_prevue, sid)
    )

    # Cascade date (and optional time) change to linked RDV
    rdv_id = row['rdv_id']
    if rdv_id:
        if heure:
            db.execute("UPDATE rdv SET date=?, heure=? WHERE id=?", (date_prevue, heure, rdv_id))
        else:
            db.execute("UPDATE rdv SET date=? WHERE id=?", (date_prevue, rdv_id))

    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/suivi/<sid>/reset', methods=['POST'])
def reset_suivi(pid, sid):
    """Reset a step back to a_faire without deleting it."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute(
        "UPDATE suivi_postop SET statut='a_faire', date_reelle='', historique_id='', notes='' WHERE id=? AND patient_id=?",
        (sid, pid)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/suivi/<sid>', methods=['DELETE'])
def delete_suivi(pid, sid):
    """Permanently delete a suivi step and its linked RDV."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute("SELECT rdv_id FROM suivi_postop WHERE id=? AND patient_id=?", (sid, pid)).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404
    if row['rdv_id']:
        db.execute("DELETE FROM rdv WHERE id=?", (row['rdv_id'],))
    db.execute("DELETE FROM suivi_postop WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


# ─── PATIENT ACCOUNT ──────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/has-account', methods=['GET'])
def has_account(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"has_account": False}), 403
    db = get_db()
    row = db.execute("SELECT id, username FROM users WHERE patient_id=? AND role='patient'", (pid,)).fetchone()
    if row:
        return jsonify({"has_account": True, "username": row['username']})
    return jsonify({"has_account": False})


@bp.route('/api/patients/<pid>/create-account', methods=['POST'])
def create_patient_account(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404
    # Check if account already exists
    existing = db.execute("SELECT id FROM users WHERE patient_id=?", (pid,)).fetchone()
    if existing:
        return jsonify({"error": "Ce patient a déjà un compte"}), 409

    data     = request.json or {}
    username = data.get('username') or f"patient.{p['prenom'].lower().replace(' ','-')}.{p['nom'].lower().replace(' ','-')}"
    password = data.get('password') or str(uuid.uuid4())[:10]

    # Ensure username is unique
    base_username = username
    counter = 1
    while db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        username = f"{base_username}{counter}"
        counter += 1

    from werkzeug.security import generate_password_hash
    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id, status) VALUES (?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), 'patient', p['nom'], p['prenom'], pid, 'active')
    )
    db.commit()

    email_sent = False
    patient_email = p['email'] if p['email'] else None
    if patient_email and '@' in patient_email:
        try:
            from email_notif import send_credentials_email
            host = request.host_url.rstrip('/')
            email_sent = send_credentials_email(
                patient_email, p['prenom'], p['nom'], username, password, host
            )
        except Exception:
            pass

    return jsonify({"ok": True, "username": username, "password": password, "email_sent": email_sent})


# ─── CLINICAL TRENDS ──────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/trends', methods=['GET'])
def get_trends(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT date, acuite_od, acuite_og, tension_od, tension_og "
        "FROM historique WHERE patient_id=? AND date!='' ORDER BY date ASC",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ─── CSV EXPORT (all patients) ────────────────────────────────────────────────

@bp.route('/api/patients/export-csv', methods=['GET'])
@require_role('medecin')
def export_patients_csv():
    from flask import Response
    u = current_user()
    db = get_db()
    rows = db.execute(
        "SELECT id, nom, prenom, ddn, sexe, telephone, email, "
        "antecedents, allergies, date_chirurgie, type_chirurgie, created_at "
        "FROM patients WHERE medecin_id=? ORDER BY nom, prenom",
        (u['id'],)
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Nom","Prénom","DDN","Sexe","Téléphone","Email",
                     "Antécédents","Allergies","Date chirurgie","Type chirurgie","Créé le"])
    for r in rows:
        p           = decrypt_patient(dict(r))
        antecedents = ', '.join(json.loads(p['antecedents'] or '[]'))
        allergies   = ', '.join(json.loads(p['allergies']   or '[]'))
        writer.writerow([
            p['id'], p['nom'], p['prenom'], p['ddn'], p['sexe'],
            p['telephone'], p['email'], antecedents, allergies,
            p['date_chirurgie'], p['type_chirurgie'], p['created_at']
        ])
    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={"Content-Disposition": "attachment; filename=patients_export.csv"}
    )


# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/audit', methods=['GET'])
@require_role('medecin')
def get_audit(pid):
    db = get_db()
    rows = db.execute(
        "SELECT a.*, u.username FROM audit_log a "
        "LEFT JOIN users u ON a.user_id = u.id "
        "WHERE a.patient_id=? ORDER BY a.created_at DESC LIMIT 100",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ─── POST-OP GAP DETECTION ───────────────────────────────────────────────────

@bp.route('/api/postop-gaps', methods=['GET'])
@require_role('medecin')
def get_postop_gaps():
    """Return all overdue post-op follow-up steps for this doctor's patients."""
    u = current_user()
    db = get_db()
    today = datetime.date.today().isoformat()
    rows = db.execute("""
        SELECT s.id, s.patient_id, s.etape, s.date_prevue, s.statut,
               p.nom, p.prenom
        FROM suivi_postop s
        JOIN patients p ON s.patient_id = p.id
        WHERE p.medecin_id = ?
          AND s.statut = 'a_faire'
          AND s.date_prevue < ?
        ORDER BY s.date_prevue ASC
    """, (u['id'], today)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['nom']    = decrypt_field(d.get('nom',    '') or '')
        d['prenom'] = decrypt_field(d.get('prenom', '') or '')
        result.append(d)
    return jsonify(result)

