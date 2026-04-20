from flask import Blueprint, request, jsonify
from database import get_db, current_user, medecin_can_access_patient
from llm import call_llm, SYSTEM_OPHTHALMO, SYSTEM_IMAGE_ANALYSIS
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


def _has_ai_consent(db, patient_id: str) -> bool:
    row = db.execute(
        "SELECT granted FROM patient_consents "
        "WHERE patient_id=? AND consent_type='ai_analysis' "
        "ORDER BY created_at DESC LIMIT 1",
        (patient_id,)
    ).fetchone()
    return bool(row and row['granted'])


@bp.route('/api/ai/question', methods=['POST'])
@limiter.limit("40 per hour; 5 per minute")
def ai_question():
    u = current_user()
    if not u:
        return jsonify({}), 401
    data       = request.json or {}
    question   = _sanitize_llm(data.get('question', ''))
    context    = (data.get('context') or '').strip()
    patient_id = (data.get('patient_id') or '').strip()

    # Patients always scope the request to themselves — never let a patient
    # interrogate another patient's consent by passing a different id.
    if u['role'] == 'patient':
        patient_id = u.get('patient_id', '')

    # If any patient-scoped context is being sent to the third-party LLM,
    # require a patient_id and verify AI consent for that patient.
    if context or patient_id:
        if not patient_id:
            return jsonify({
                "error": "patient_id requis lorsqu'un contexte patient est fourni.",
                "consent_required": True,
            }), 400
        db = get_db()
        if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], patient_id):
            return jsonify({"error": "Accès refusé"}), 403
        if not _has_ai_consent(db, patient_id):
            return jsonify({
                "error": "Consentement IA requis pour ce patient avant d'envoyer des données cliniques à l'IA.",
                "consent_required": True,
            }), 403
        prompt = f"{question}\n\nContexte patient : {_sanitize_llm(context, max_len=500)}"
    else:
        prompt = question

    answer = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=800)
    return jsonify({"answer": answer})


@bp.route('/api/ai/analyze-image', methods=['POST'])
@limiter.limit("20 per hour; 3 per minute")
def ai_analyze():
    """Disabled — clinical images are not sent to the LLM. Only documents
    (PDFs, reports) can be analyzed, via /api/patients/<pid>/documents/<doc_id>/analyze."""
    return jsonify({
        "error": "L'analyse IA des images cliniques est désactivée. Seuls les documents (PDF) peuvent être analysés."
    }), 400
