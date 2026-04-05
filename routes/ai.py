from flask import Blueprint, request, jsonify
from database import get_db, current_user
from llm import call_llm, SYSTEM_OPHTHALMO

bp = Blueprint('ai', __name__)


@bp.route('/api/ai/question', methods=['POST'])
def ai_question():
    u = current_user()
    if not u:
        return jsonify({}), 401
    data   = request.json or {}
    answer = call_llm(data.get('question', ''), SYSTEM_OPHTHALMO, max_tokens=800)
    return jsonify({"answer": answer})


@bp.route('/api/ai/analyze-image', methods=['POST'])
def ai_analyze():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    img_type  = data.get('type', 'imagerie ophtalmologique')
    context   = data.get('context', '')
    doc_id    = data.get('doc_id', '')
    patient_id = data.get('patient_id', '')

    image_b64 = None
    if doc_id and patient_id:
        db  = get_db()
        row = db.execute(
            "SELECT image_b64 FROM documents WHERE id=? AND patient_id=?", (doc_id, patient_id)
        ).fetchone()
        if row:
            image_b64 = row['image_b64']

    prompt = (
        f"Analysez cette image d'ophtalmologie de type '{img_type}'. "
        f"Contexte patient : {context}. "
        f"Décrivez les éléments cliniques observables, les anomalies éventuelles, "
        f"et formulez vos recommandations diagnostiques et thérapeutiques."
    )
    analysis = call_llm(prompt, SYSTEM_OPHTHALMO, image_b64=image_b64, max_tokens=800)
    return jsonify({"analysis": analysis})
