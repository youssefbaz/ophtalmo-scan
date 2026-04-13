"""
routes/patients_import.py — CSV import/export, global search, audit log, and post-op gap detection.
"""
import json, hashlib, re, csv, io, datetime, logging
from flask import Blueprint, request, jsonify, Response
from database import get_db, current_user, add_notif, require_role, log_audit
from llm import call_llm, SYSTEM_IMPORT
from security_utils import decrypt_patient, decrypt_field, encrypt_patient_fields, sanitize
from routes.patients_helpers import _build_patient, _anonymize, _auto_create_account, _next_patient_id, _assert_owns_patient

logger = logging.getLogger(__name__)

bp = Blueprint('patients_import', __name__)


@bp.route('/api/import/csv', methods=['POST'])
def import_csv():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data     = request.json or {}
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
            pid    = _next_patient_id(db)
            nom    = sanitize(pd_data.get("nom",""),    max_len=100)
            prenom = sanitize(pd_data.get("prenom",""), max_len=100)
            email  = sanitize(pd_data.get("email",""),  max_len=200)
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
            creds = _auto_create_account(db, pid, nom=nom, prenom=prenom, email=email, app_host=host)
            added.append({"id": pid, "nom": nom, "prenom": prenom, "credentials": creds})
        db.commit()
        add_notif(db, "import", f"{len(added)} patient(s) importés depuis CSV", "medecin")
        return jsonify({"ok": True, "added": added, "count": len(added)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Impossible de parser: {e}", "raw": result_str[:500]})


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
        "code":           hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe":           p["sexe"],
        "age":            datetime.datetime.now().year - int(p["ddn"][:4]) if p.get("ddn") else 0,
        "antecedents":    p["antecedents"],
        "allergies":      p["allergies"],
        "date_chirurgie": p.get("date_chirurgie",""),
        "type_chirurgie": p.get("type_chirurgie",""),
        "historique":     [{k: v for k, v in h.items() if k != 'medecin'} for h in p["historique"]],
        "nb_rdv":         len(p["rdv"]),
        "export_date":    datetime.datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(anon)


@bp.route('/api/patients/export-csv', methods=['GET'])
@require_role('medecin')
def export_patients_csv():
    u = current_user()
    db = get_db()
    rows = db.execute(
        "SELECT id, nom, prenom, ddn, sexe, telephone, email, "
        "antecedents, allergies, date_chirurgie, type_chirurgie, created_at "
        "FROM patients WHERE medecin_id=? AND (deleted IS NULL OR deleted=0) ORDER BY nom, prenom",
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

    scope_where  = "WHERE p.medecin_id=? AND (p.deleted IS NULL OR p.deleted=0)" if u['role'] == 'medecin' else "WHERE (p.deleted IS NULL OR p.deleted=0)"
    scope_params = (u['id'],) if u['role'] == 'medecin' else ()
    pat_rows = db.execute(
        f"SELECT id, nom, prenom, ddn FROM patients p {scope_where}", scope_params
    ).fetchall()
    for r in pat_rows:
        dec     = decrypt_patient(dict(r))
        nom_l   = (dec['nom']    or '').lower()
        prenom_l = (dec['prenom'] or '').lower()
        id_l    = (dec['id']     or '').lower()
        if q in nom_l or q in prenom_l or q in id_l:
            results.append({
                "type":  "patient", "pid": dec["id"],
                "label": f"{dec['prenom']} {dec['nom']}",
                "sub":   f"Patient · {dec['ddn'] or '—'}"
            })

    del_filter = "AND (h.deleted IS NULL OR h.deleted=0)"
    scope_join = (
        f"JOIN patients p ON h.patient_id=p.id WHERE p.medecin_id=? {del_filter}"
        if u['role'] == 'medecin' else
        f"JOIN patients p ON h.patient_id=p.id WHERE 1=1 {del_filter}"
    )
    scope_params2 = (u['id'],) if u['role'] == 'medecin' else ()
    hist_rows = db.execute(
        f"SELECT h.id, h.patient_id, h.date, h.motif, h.diagnostic, p.nom, p.prenom "
        f"FROM historique h {scope_join} "
        f"AND (lower(h.motif) LIKE ? OR lower(h.diagnostic) LIKE ? OR lower(h.notes) LIKE ?)",
        scope_params2 + (ql, ql, ql)
    ).fetchall()
    for r in hist_rows:
        dec = decrypt_patient({"nom": r["nom"], "prenom": r["prenom"]})
        results.append({
            "type":  "consultation", "pid": r["patient_id"],
            "label": f"{r['motif'] or r['diagnostic'] or 'Consultation'}",
            "sub":   f"{dec['prenom']} {dec['nom']} · {r['date']}"
        })

    return jsonify(results[:12])


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
          AND (p.deleted IS NULL OR p.deleted = 0)
        ORDER BY s.date_prevue ASC
    """, (u['id'], today)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['nom']    = decrypt_field(d.get('nom',    '') or '')
        d['prenom'] = decrypt_field(d.get('prenom', '') or '')
        result.append(d)
    return jsonify(result)
