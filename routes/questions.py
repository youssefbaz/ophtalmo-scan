import uuid, datetime, json, logging, os
from flask import Blueprint, request, jsonify, Response
from database import get_db, current_user, add_notif, medecin_can_access_patient
from llm import call_llm, LLMUnavailableError, SYSTEM_RESPONSE_DRAFT
from security_utils import decrypt_patient, decrypt_clinical, encrypt_question_fields, decrypt_question_fields
from routes._audio import (
    save_audio, load_audio, detect_audio_mime, read_audio_from_request,
)

logger = logging.getLogger(__name__)

bp = Blueprint('questions', __name__)


def _fmt_question(q: dict) -> dict:
    q['reponse_validee'] = bool(q.get('reponse_validee'))
    q['has_question_audio'] = bool((q.get('question_audio_path') or '').strip())
    q['has_reponse_audio']  = bool((q.get('reponse_audio_path')  or '').strip())
    q['question_audio_duration'] = int(q.get('question_audio_duration') or 0)
    q['reponse_audio_duration']  = int(q.get('reponse_audio_duration')  or 0)
    # Don't leak filesystem paths
    q.pop('question_audio_path', None)
    q.pop('reponse_audio_path',  None)
    return q


def _read_payload():
    """Accept JSON or multipart. Returns (text_value, audio_bytes, duration, error_tuple_or_None)."""
    text = ''
    if request.content_type and request.content_type.startswith('multipart/'):
        text = (request.form.get('question') or request.form.get('reponse') or '').strip()
    else:
        data = request.get_json(silent=True) or {}
        text = (data.get('question') or data.get('reponse') or '').strip()
    audio_bytes, duration, err = read_audio_from_request()
    if err:
        return text, b'', 0, (jsonify({"error": err[0]}), err[1])
    return text, audio_bytes, duration, None


@bp.route('/api/patients/<pid>/questions', methods=['GET'])
def get_questions(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    rows = db.execute(
        "SELECT * FROM questions WHERE patient_id=? AND deleted=0 ORDER BY date DESC", (pid,)
    ).fetchall()
    result = [_fmt_question(decrypt_question_fields(dict(r))) for r in rows]
    return jsonify(result)


@bp.route('/api/patients/<pid>/questions', methods=['POST'])
def add_question(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    p_row = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p_row:
        return jsonify({"error": "Non trouvé"}), 404
    p = decrypt_patient(dict(p_row))

    question_text, audio_bytes, duration, err = _read_payload()
    if err:
        return err
    if not question_text and not audio_bytes:
        return jsonify({"error": "La question ne peut pas être vide"}), 400

    # LLM draft only runs when there's a text question AND consent is granted
    reponse_ia = ""
    if question_text:
        _consent_row = db.execute(
            "SELECT granted FROM patient_consents "
            "WHERE patient_id=? AND consent_type='ai_analysis' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,)
        ).fetchone()
        has_consent = bool(_consent_row and _consent_row['granted'])
        if has_consent:
            derniere_row = db.execute(
                "SELECT * FROM historique WHERE patient_id=? ORDER BY date DESC LIMIT 1", (pid,)
            ).fetchone()
            derniere    = decrypt_clinical(dict(derniere_row)) if derniere_row else None
            antecedents = json.loads(p['antecedents'] or '[]')
            allergies   = json.loads(p['allergies']   or '[]')
            age = (datetime.datetime.now().year - int(p['ddn'][:4])
                   if (p.get('ddn') and p['ddn'][:4].isdigit()) else 0)
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
            except LLMUnavailableError as e:
                logger.error(f"LLM question draft failed: {e}")
            except Exception as e:
                logger.error(f"LLM question draft unexpected error: {e}")

    qid = "Q" + str(uuid.uuid4())[:6].upper()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    enc = encrypt_question_fields({"question": question_text, "reponse_ia": reponse_ia})
    audio_path = save_audio('questions', qid, audio_bytes) if audio_bytes else ''

    db.execute(
        "INSERT INTO questions "
        "(id,patient_id,question,date,statut,reponse,reponse_ia,reponse_validee,"
        " question_audio_path,question_audio_duration) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (qid, pid, enc['question'], now, 'en_attente', '', enc['reponse_ia'], 0,
         audio_path, int(duration or 0))
    )
    db.commit()

    add_notif(db, "question",
              f"❓ {p.get('prenom','')} {p.get('nom','')} a posé une question",
              "patient", pid, {"question_id": qid, "has_audio": bool(audio_path)})

    return jsonify({
        "ok": True,
        "question": {
            "id": qid, "question": question_text, "date": now,
            "statut": "en_attente", "reponse": "",
            "reponse_ia": reponse_ia, "reponse_validee": False,
            "has_question_audio": bool(audio_path),
            "question_audio_duration": int(duration or 0),
            "has_reponse_audio": False,
            "reponse_audio_duration": 0,
        }
    })


@bp.route('/api/patients/<pid>/questions/<qid>/repondre', methods=['POST'])
def repondre_question(pid, qid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    q = db.execute(
        "SELECT * FROM questions WHERE id=? AND patient_id=?", (qid, pid)
    ).fetchone()
    if not q:
        return jsonify({}), 404

    reponse_text, audio_bytes, duration, err = _read_payload()
    if err:
        return err
    if not reponse_text and not audio_bytes:
        # Fallback to validating the AI draft
        q_dec = decrypt_question_fields(dict(q))
        reponse_text = q_dec.get('reponse_ia') or ''
        if not reponse_text:
            return jsonify({"error": "La réponse ne peut pas être vide"}), 400

    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    enc_rep = encrypt_question_fields({"reponse": reponse_text})
    audio_path = save_audio('questions', f"{qid}_rep", audio_bytes) if audio_bytes else ''

    db.execute(
        "UPDATE questions SET reponse=?, reponse_validee=1, statut='répondu', "
        "repondu_par=?, date_reponse=?, reponse_audio_path=?, reponse_audio_duration=? "
        "WHERE id=?",
        (enc_rep['reponse'], u['nom'], now, audio_path, int(duration or 0), qid)
    )
    db.commit()
    add_notif(db, "reponse", "Le médecin a répondu à votre question", "medecin", pid)
    return jsonify({
        "ok": True,
        "has_reponse_audio": bool(audio_path),
        "reponse_audio_duration": int(duration or 0),
    })


@bp.route('/api/patients/<pid>/questions/<qid>', methods=['DELETE'])
def delete_question(pid, qid):
    """Soft-delete a question. Doctor can archive answered questions; patient can delete their own unanswered draft."""
    u = current_user()
    if not u:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    q = db.execute(
        "SELECT statut, question_audio_path, reponse_audio_path, patient_id "
        "FROM questions WHERE id=? AND patient_id=?",
        (qid, pid)
    ).fetchone()
    if not q:
        return jsonify({"error": "Non trouvé"}), 404

    if u['role'] == 'patient':
        if u.get('patient_id') != pid:
            return jsonify({"error": "Accès refusé"}), 403
        if q['statut'] != 'en_attente':
            return jsonify({"error": "Impossible de supprimer une question déjà traitée"}), 400
    else:
        if u['role'] != 'medecin':
            return jsonify({"error": "Accès refusé"}), 403
        if not medecin_can_access_patient(db, u['id'], pid):
            return jsonify({"error": "Accès refusé"}), 403
        if q['statut'] == 'en_attente':
            return jsonify({"error": "Impossible de supprimer une question sans réponse"}), 400

    db.execute(
        "UPDATE questions SET deleted=1, deleted_at=? WHERE id=?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), qid)
    )
    db.commit()
    for p in (q['question_audio_path'], q['reponse_audio_path']):
        if p and os.path.exists(p):
            try: os.remove(p)
            except OSError: pass
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/questions/deleted', methods=['GET'])
def get_deleted_questions(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    db = get_db()
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify([]), 403
    rows = db.execute(
        "SELECT * FROM questions WHERE patient_id=? AND deleted=1 ORDER BY deleted_at DESC", (pid,)
    ).fetchall()
    result = [_fmt_question(decrypt_question_fields(dict(r))) for r in rows]
    return jsonify(result)


@bp.route('/api/questions/<qid>/audio/<kind>', methods=['GET'])
def get_question_audio(qid, kind):
    """Stream question or response audio. `kind` is 'question' or 'reponse'."""
    if kind not in ('question', 'reponse'):
        return jsonify({"error": "kind invalide"}), 400
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    row = db.execute(
        "SELECT patient_id, question_audio_path, reponse_audio_path "
        "FROM questions WHERE id=? AND deleted=0",
        (qid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Question non trouvée"}), 404

    if u['role'] == 'patient' and u.get('patient_id') != row['patient_id']:
        return jsonify({"error": "Accès refusé"}), 403
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], row['patient_id']):
        return jsonify({"error": "Accès refusé"}), 403

    path = (row['question_audio_path'] if kind == 'question' else row['reponse_audio_path']) or ''
    if not path or not os.path.exists(path):
        return jsonify({"error": "Audio non trouvé"}), 404
    try:
        raw = load_audio(path)
    except Exception as e:
        logger.warning("question audio decrypt failed for %s/%s: %s", qid, kind, e)
        return jsonify({"error": "Lecture audio impossible"}), 500

    mime = detect_audio_mime(raw[:32]) or 'audio/webm'
    return Response(raw, mimetype=mime, headers={
        "Cache-Control": "private, max-age=0, no-store",
        "Content-Length": str(len(raw)),
    })
