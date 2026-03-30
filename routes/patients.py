import json, datetime, hashlib, re, csv, io, uuid
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif
from llm import call_llm, SYSTEM_IMPORT

bp = Blueprint('patients', __name__)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _build_patient(db, pid, strip_images=True):
    """Assemble a full patient dict from all DB tables."""
    row = db.execute("SELECT * FROM patients WHERE id = ?", (pid,)).fetchone()
    if not row:
        return None
    p = dict(row)
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
        db.execute("SELECT * FROM documents WHERE patient_id=? AND source='imagerie'", (pid,))]
    docs = [dict(r) for r in
        db.execute("SELECT * FROM documents WHERE patient_id=? AND source='document'", (pid,))]
    if strip_images:
        for item in imgs + docs:
            item.pop('image_b64', None)
    p['imagerie']  = imgs
    p['documents'] = docs

    questions = [dict(r) for r in
        db.execute("SELECT * FROM questions WHERE patient_id=? ORDER BY date DESC", (pid,))]
    for q in questions:
        q['reponse_validee'] = bool(q['reponse_validee'])
    p['questions'] = questions

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


def _next_patient_id(db):
    row = db.execute("SELECT COUNT(*) FROM patients").fetchone()
    return "P" + str(1000 + row[0]).zfill(3)


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
        return jsonify([dict(row)] if row else [])

    if u['role'] == 'assistant':
        pids = [r['id'] for r in db.execute("SELECT id FROM patients").fetchall()]
        return jsonify([_anonymize(_build_patient(db, pid)) for pid in pids])

    # médecin — full list with optional search
    rows = db.execute("SELECT * FROM patients").fetchall()
    result = []
    for row in rows:
        p = dict(row)
        p['antecedents'] = json.loads(p['antecedents'] or '[]')
        if q and not (q in p['nom'].lower() or q in p['prenom'].lower() or q in p['id'].lower()):
            continue
        nb_urgent = db.execute(
            "SELECT COUNT(*) FROM rdv WHERE patient_id=? AND urgent=1 AND statut='en_attente'",
            (p['id'],)
        ).fetchone()[0]
        result.append({
            "id": p['id'], "nom": p['nom'], "prenom": p['prenom'],
            "ddn": p['ddn'], "antecedents": p['antecedents'][:2],
            "nb_rdv_urgent": nb_urgent
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
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404

    if u['role'] == 'assistant':
        return jsonify(_anonymize(p))

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
def add_patient():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    pid = _next_patient_id(db)
    db.execute(
        "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pid,
         data.get("nom",""), data.get("prenom",""), data.get("ddn",""), data.get("sexe",""),
         data.get("telephone",""), data.get("email",""),
         json.dumps(data.get("antecedents",[])), json.dumps(data.get("allergies",[])))
    )
    db.commit()
    add_notif(db, "patient_added",
              f"Nouveau patient ajouté : {data.get('prenom','')} {data.get('nom','')}",
              "medecin", pid)
    return jsonify({"ok": True, "id": pid}), 201


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
    p = db.execute("SELECT prenom, nom FROM patients WHERE id=?", (pid,)).fetchone()
    if p:
        add_notif(db, "chirurgie",
                  f"✂️ Chirurgie planifiée pour {p['prenom']} {p['nom']} : {data.get('date_chirurgie','')}",
                  "medecin", pid)
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/export', methods=['GET'])
def export_patient(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
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

    result_str = call_llm(prompt, SYSTEM_IMPORT, max_tokens=1500)
    db = get_db()
    try:
        clean = re.sub(r'```(?:json)?|```', '', result_str).strip()
        patients_list = json.loads(clean)
        added = []
        for pd_data in patients_list:
            pid = _next_patient_id(db)
            db.execute(
                "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, pd_data.get("nom",""), pd_data.get("prenom",""), pd_data.get("ddn",""),
                 pd_data.get("sexe",""), pd_data.get("telephone",""), pd_data.get("email",""),
                 json.dumps(pd_data.get("antecedents",[])), json.dumps(pd_data.get("allergies",[])))
            )
            added.append({"id": pid, "nom": pd_data.get("nom",""), "prenom": pd_data.get("prenom","")})
        db.commit()
        add_notif(db, "import", f"{len(added)} patient(s) importés depuis CSV", "medecin")
        return jsonify({"ok": True, "added": added, "count": len(added)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Impossible de parser: {e}", "raw": result_str[:500]})


@bp.route('/api/import/image', methods=['POST'])
def import_image():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    return jsonify({"ok": False, "error": "L'import par image n'est pas disponible. Utilisez l'import CSV."})
