from flask import Blueprint, request, jsonify
from database import current_user
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
    return jsonify({
        "analysis": ("⚠️ L'analyse automatique d'images n'est pas disponible dans cette version. "
                     "Veuillez saisir vos observations manuellement dans les notes du patient.")
    })
