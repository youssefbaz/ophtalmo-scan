import uuid, datetime, json, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif, require_role
from llm import call_llm, SYSTEM_OPHTHALMO

logger = logging.getLogger(__name__)

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
        "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,"
        "(CASE WHEN image_b64 != '' AND image_b64 IS NOT NULL THEN 1 ELSE 0 END) AS has_image "
        "FROM documents WHERE patient_id=? AND source='document' AND deleted=0",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/documents/deleted', methods=['GET'])
def get_deleted_documents(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    db = get_db()
    rows = db.execute(
        "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,"
        "(CASE WHEN image_b64 != '' AND image_b64 IS NOT NULL THEN 1 ELSE 0 END) AS has_image "
        "FROM documents WHERE patient_id=? AND deleted=1 ORDER BY deleted_at DESC",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/documents/<doc_id>', methods=['GET'])
def get_document(pid, doc_id):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
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
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if p['ddn'] else 0
    context = (f"Patient : {p['prenom']} {p['nom']}, {age} ans. "
               f"Antécédents : {', '.join(antecedents) or 'aucun renseigné'}")
    uploader = "le patient" if doc['uploaded_by'] == 'patient' else "le médecin"

    image_b64 = doc['image_b64'] or None
    if image_b64:
        prompt = (f"Analysez cette image ophtalmologique de type '{doc['type']}' uploadée par {uploader}. "
                  f"Contexte : {context}. "
                  f"Décrivez précisément les éléments cliniques visibles (structure, anomalies, lésions), "
                  f"formulez une impression diagnostique et des recommandations thérapeutiques.")
    else:
        prompt = (f"{uploader.capitalize()} a uploadé un document de type '{doc['type']}'. "
                  f"Contexte : {context}. "
                  f"Donnez les points de vigilance clinique et les recommandations générales.")

    try:
        analysis = call_llm(prompt, SYSTEM_OPHTHALMO, image_b64=image_b64, max_tokens=800)
    except Exception as e:
        logger.error(f"LLM analyze failed: {e}")
        return jsonify({"error": "Service IA indisponible, réessayez dans quelques minutes."}), 503
    db.execute("UPDATE documents SET analyse_ia=?, valide=1 WHERE id=?", (analysis, doc_id))
    db.commit()
    return jsonify({"ok": True, "analysis": analysis})


@bp.route('/api/patients/<pid>/documents/<doc_id>', methods=['DELETE'])
def delete_document(pid, doc_id):
    """Soft-delete: marks as deleted, keeps image_b64 in storage."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if not db.execute("SELECT id FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone():
        return jsonify({"error": "Non trouvé"}), 404
    db.execute(
        "UPDATE documents SET deleted=1, deleted_at=? WHERE id=?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), doc_id)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/documents/<doc_id>/restore', methods=['POST'])
def restore_document(pid, doc_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute(
        "UPDATE documents SET deleted=0, deleted_at='' WHERE id=? AND patient_id=?",
        (doc_id, pid)
    )
    db.commit()
    return jsonify({"ok": True})


# ─── AI CONSULTATION SUMMARY ──────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/consultation-summary', methods=['POST'])
@require_role('medecin')
def consultation_summary(pid):
    """Generate an AI-written clinical summary from the latest consultation."""
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404

    data = request.json or {}
    hid  = data.get('historique_id')

    if hid:
        h = db.execute("SELECT * FROM historique WHERE id=? AND patient_id=?", (hid, pid)).fetchone()
    else:
        h = db.execute(
            "SELECT * FROM historique WHERE patient_id=? ORDER BY date DESC LIMIT 1", (pid,)
        ).fetchone()

    if not h:
        return jsonify({"error": "Aucune consultation disponible"}), 404

    antecedents = json.loads(p['antecedents'] or '[]')
    allergies   = json.loads(p['allergies']   or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if p.get('ddn') else 0

    def _safe(val):
        """Strip prompt-injection attempts from free-text DB fields."""
        if val is None:
            return ''
        return str(val).replace('```', '').replace('<|', '').replace('|>', '')

    prompt = (
        "Génère un compte-rendu de consultation ophtalmologique structuré et professionnel "
        "à partir des données cliniques suivantes (données issues du dossier médical) :\n\n"
        f"[DONNÉES PATIENT]\n"
        f"Nom : {p['prenom']} {p['nom']}\n"
        f"Age : {age} ans\n"
        f"Sexe : {p['sexe']}\n"
        f"Antécédents : {', '.join(antecedents) or 'aucun renseigné'}\n"
        f"Allergies : {', '.join(allergies) if allergies else 'Aucune'}\n\n"
        f"[DONNÉES CONSULTATION]\n"
        f"Date : {h['date']}\n"
        f"Motif : {_safe(h['motif'])}\n"
        f"Acuité OD : {_safe(h['acuite_od'])} | OG : {_safe(h['acuite_og'])}\n"
        f"Tonus OD : {_safe(h['tension_od'])} mmHg | OG : {_safe(h['tension_og'])} mmHg\n"
        f"Réfraction OD : S {_safe(h['refraction_od_sph'])} C {_safe(h['refraction_od_cyl'])} Axe {_safe(h['refraction_od_axe'])}\n"
        f"Réfraction OG : S {_safe(h['refraction_og_sph'])} C {_safe(h['refraction_og_cyl'])} Axe {_safe(h['refraction_og_axe'])}\n"
        f"Segment antérieur : {_safe(h['segment_ant']) or 'non renseigné'}\n"
        f"Diagnostic : {_safe(h['diagnostic'])}\n"
        f"Traitement : {_safe(h['traitement'])}\n"
        f"Notes : {_safe(h['notes']) or 'aucune'}\n\n"
        "[FIN DES DONNÉES]\n\n"
        "Rédige un compte-rendu complet, clair et structuré en français, prêt à être transmis ou archivé."
    )

    try:
        summary = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=1000)
    except Exception as e:
        logger.error(f"LLM summary failed: {e}")
        return jsonify({"error": "Service IA indisponible, réessayez dans quelques minutes."}), 503

    return jsonify({"ok": True, "summary": summary})
