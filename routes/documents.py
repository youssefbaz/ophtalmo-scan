import uuid, datetime, json
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif
from llm import call_llm, SYSTEM_OPHTHALMO

bp = Blueprint('documents', __name__)


@bp.route('/api/patients/<pid>/upload', methods=['POST'])
def upload_document(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404

    data     = request.json or {}
    doc_id   = "DOC" + str(uuid.uuid4())[:6].upper()
    doc_type = data.get('type', 'Document')
    source   = 'imagerie' if u['role'] != 'patient' else 'document'

    db.execute(
        "INSERT INTO documents (id,patient_id,type,date,description,uploaded_by,valide,image_b64,source) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (doc_id, pid, doc_type,
         datetime.datetime.now().strftime("%Y-%m-%d"),
         data.get('description',''), u['role'],
         1 if u['role'] == 'medecin' else 0,
         data.get('image',''), source)
    )
    db.commit()

    if u['role'] == 'patient':
        add_notif(db, "document_uploaded",
                  f"📎 {p['prenom']} {p['nom']} a uploadé : {doc_type}",
                  "patient", pid, {"doc_id": doc_id})

    return jsonify({"ok": True, "id": doc_id})


@bp.route('/api/patients/<pid>/documents', methods=['GET'])
def get_documents(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source "
        "FROM documents WHERE patient_id=? AND source='document'",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/documents/<doc_id>', methods=['GET'])
def get_document(pid, doc_id):
    u = current_user()
    if not u:
        return jsonify({}), 401
    db = get_db()
    row = db.execute(
        "SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)
    ).fetchone()
    if not row:
        return jsonify({}), 404
    return jsonify(dict(row))


@bp.route('/api/patients/<pid>/documents/<doc_id>/analyze', methods=['POST'])
def analyze_document(pid, doc_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p   = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    doc = db.execute("SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone()
    if not p or not doc:
        return jsonify({}), 404

    antecedents = json.loads(p['antecedents'] or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if p.get('ddn') else 0
    context = (f"Patient : {p['prenom']} {p['nom']}, {age} ans. "
               f"Antécédents : {', '.join(antecedents)}")
    prompt = (f"Le médecin a uploadé un document de type '{doc['type']}'. "
              f"Décrivez les éléments cliniques à vérifier et les recommandations générales. "
              f"Contexte : {context}")

    analysis = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=600)
    db.execute("UPDATE documents SET analyse_ia=?, valide=1 WHERE id=?", (analysis, doc_id))
    db.commit()
    return jsonify({"ok": True, "analysis": analysis})
