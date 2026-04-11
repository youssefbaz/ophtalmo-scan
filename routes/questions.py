import uuid, datetime, json, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif
from llm import call_llm, SYSTEM_RESPONSE_DRAFT
from security_utils import decrypt_patient

logger = logging.getLogger(__name__)

bp = Blueprint('questions', __name__)


@bp.route('/api/patients/<pid>/questions', methods=['GET'])
def get_questions(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM questions WHERE patient_id=? AND deleted=0 ORDER BY date DESC", (pid,)
    ).fetchall()
    result = [dict(r) for r in rows]
    for q in result:
        q['reponse_validee'] = bool(q['reponse_validee'])
    return jsonify(result)


@bp.route('/api/patients/<pid>/questions', methods=['POST'])
def add_question(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p_row = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p_row:
        return jsonify({"error": "Non trouvé"}), 404
    p = decrypt_patient(dict(p_row))

    data          = request.json or {}
    question_text = data.get('question', '')

    # Fetch last consultation for LLM context
    derniere    = db.execute(
        "SELECT * FROM historique WHERE patient_id=? ORDER BY date DESC LIMIT 1", (pid,)
    ).fetchone()
    antecedents = json.loads(p['antecedents'] or '[]')
    allergies   = json.loads(p['allergies']   or '[]')
    age         = datetime.datetime.now().year - int(p['ddn'][:4]) if (p.get('ddn') and p['ddn'][:4].isdigit()) else 0

    context = f"""Patient : {p['prenom']} {p['nom']}, {age} ans, {p['sexe']}.
Antécédents : {', '.join(antecedents)}.
Allergies : {', '.join(allergies) if allergies else 'Aucune'}.
Traitements en cours : {derniere['traitement'] if derniere else 'Non renseigné'}.
Dernière consultation ({derniere['date'] if derniere else 'N/A'}) : {derniere['diagnostic'] if derniere else 'N/A'}.
Acuité OD : {derniere['acuite_od'] if derniere else 'N/A'} | OG : {derniere['acuite_og'] if derniere else 'N/A'}.
Tonus OD : {derniere['tension_od'] if derniere else 'N/A'} | OG : {derniere['tension_og'] if derniere else 'N/A'}."""

    try:
        reponse_ia = call_llm(
            f"Question du patient : {question_text}\nContexte : {context}",
            SYSTEM_RESPONSE_DRAFT, max_tokens=400
        )
    except Exception as e:
        logger.error(f"LLM question draft failed: {e}")
        reponse_ia = "⚠️ Service IA indisponible. Votre question a été enregistrée et sera traitée par le médecin."

    qid = "Q" + str(uuid.uuid4())[:6].upper()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO questions (id,patient_id,question,date,statut,reponse,reponse_ia,reponse_validee) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (qid, pid, question_text, now, 'en_attente', '', reponse_ia, 0)
    )
    db.commit()

    add_notif(db, "question",
              f"❓ {p.get('prenom','')} {p.get('nom','')} a posé une question",
              "patient", pid, {"question_id": qid})

    return jsonify({
        "ok": True,
        "question": {
            "id": qid, "question": question_text, "date": now,
            "statut": "en_attente", "reponse": "",
            "reponse_ia": reponse_ia, "reponse_validee": False
        }
    })


@bp.route('/api/patients/<pid>/questions/<qid>/repondre', methods=['POST'])
def repondre_question(pid, qid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    q = db.execute(
        "SELECT * FROM questions WHERE id=? AND patient_id=?", (qid, pid)
    ).fetchone()
    if not q:
        return jsonify({}), 404

    data    = request.json or {}
    reponse = data.get('reponse', q['reponse_ia'] or '')
    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    db.execute(
        "UPDATE questions SET reponse=?, reponse_validee=1, statut='répondu', "
        "repondu_par=?, date_reponse=? WHERE id=?",
        (reponse, u['nom'], now, qid)
    )
    db.commit()
    add_notif(db, "reponse", "Le médecin a répondu à votre question", "medecin", pid)
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/questions/<qid>', methods=['DELETE'])
def delete_question(pid, qid):
    """Soft-delete an answered question — keeps it in history."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    q = db.execute(
        "SELECT statut FROM questions WHERE id=? AND patient_id=?", (qid, pid)
    ).fetchone()
    if not q:
        return jsonify({"error": "Non trouvé"}), 404
    if q['statut'] == 'en_attente':
        return jsonify({"error": "Impossible de supprimer une question sans réponse"}), 400
    db.execute(
        "UPDATE questions SET deleted=1, deleted_at=? WHERE id=?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), qid)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/questions/deleted', methods=['GET'])
def get_deleted_questions(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM questions WHERE patient_id=? AND deleted=1 ORDER BY deleted_at DESC", (pid,)
    ).fetchall()
    result = [dict(r) for r in rows]
    for q in result:
        q['reponse_validee'] = bool(q['reponse_validee'])
    return jsonify(result)
