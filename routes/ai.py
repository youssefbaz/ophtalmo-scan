from flask import Blueprint, request, jsonify
from database import get_db, current_user
from llm import call_llm, SYSTEM_OPHTHALMO
from extensions import limiter

bp = Blueprint('ai', __name__)

_LLM_MAX_INPUT = 2000  # max chars for any user-supplied free-text before LLM


def _sanitize_llm(text: str, max_len: int = _LLM_MAX_INPUT) -> str:
    """Strip prompt-injection markers and cap length for LLM inputs."""
    if not text:
        return ''
    cleaned = (str(text)
               .replace('```', '')
               .replace('<|', '')
               .replace('|>', '')
               .replace('[INST]', '')
               .replace('[/INST]', '')
               .replace('###', ''))
    return cleaned[:max_len]


@bp.route('/api/ai/question', methods=['POST'])
@limiter.limit("40 per hour; 5 per minute")
def ai_question():
    u = current_user()
    if not u:
        return jsonify({}), 401
    data     = request.json or {}
    question = _sanitize_llm(data.get('question', ''))
    answer   = call_llm(question, SYSTEM_OPHTHALMO, max_tokens=800)
    return jsonify({"answer": answer})


@bp.route('/api/ai/analyze-image', methods=['POST'])
@limiter.limit("20 per hour; 3 per minute")
def ai_analyze():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    img_type   = _sanitize_llm(data.get('type', 'imagerie ophtalmologique'), max_len=100)
    context    = _sanitize_llm(data.get('context', ''), max_len=500)
    doc_id     = data.get('doc_id', '')
    patient_id = data.get('patient_id', '')

    image_b64 = None
    if doc_id and patient_id:
        db  = get_db()
        # Check ai_analysis consent before proceeding
        consent_row = db.execute(
            "SELECT granted FROM patient_consents "
            "WHERE patient_id=? AND consent_type='ai_analysis' "
            "ORDER BY created_at DESC LIMIT 1",
            (patient_id,)
        ).fetchone()
        if not consent_row or not consent_row['granted']:
            return jsonify({
                "error": "Consentement IA requis pour ce patient.",
                "consent_required": True
            }), 403
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
