import uuid, datetime, threading, logging, os, base64
from flask import Blueprint, request, jsonify, current_app, Response
from database import get_db, current_user, add_notif, medecin_can_access_patient
from security_utils import encrypt_field, decrypt_field, decrypt_patient

logger = logging.getLogger(__name__)

bp = Blueprint('messages', __name__)


# ─── AUDIO STORAGE ───────────────────────────────────────────────────────────
_AUDIO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'uploads', 'messages'
)
_AUDIO_MAX_BYTES = 8 * 1024 * 1024   # 8 MB — ~8 min of opus
_AUDIO_MAX_SECONDS = 180             # 3 min cap — enforced client-side, sanity-checked here

# (magic_bytes, mime, offset)
_ALLOWED_AUDIO_MAGIC = [
    (b'\x1aE\xdf\xa3',  'audio/webm', 0),   # EBML / WebM / Matroska container
    (b'OggS',           'audio/ogg',  0),
    (b'ID3',            'audio/mpeg', 0),
    (b'\xff\xfb',       'audio/mpeg', 0),   # MP3 without ID3
    (b'\xff\xf3',       'audio/mpeg', 0),
    (b'\xff\xf2',       'audio/mpeg', 0),
]


def _detect_audio_mime(raw: bytes) -> str | None:
    for magic, mime, off in _ALLOWED_AUDIO_MAGIC:
        if raw[off:off + len(magic)] == magic:
            return mime
    return None


def _save_audio_file(mid: str, raw_bytes: bytes) -> str:
    """Fernet-encrypt the audio bytes (base64-wrapped) and write to disk."""
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    path = os.path.join(_AUDIO_DIR, f"{mid}.enc")
    payload_b64 = base64.b64encode(raw_bytes).decode('ascii')
    encrypted = encrypt_field(payload_b64)
    with open(path, 'w', encoding='ascii') as f:
        f.write(encrypted)
    return path


def _load_audio_bytes(path: str) -> bytes:
    with open(path, 'r', encoding='ascii') as f:
        encrypted = f.read().strip()
    return base64.b64decode(decrypt_field(encrypted))


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _enc(text: str) -> str:
    return encrypt_field(text) if text else ''


def _dec(text: str) -> str:
    return decrypt_field(text) if text else ''


def _fmt_msg(row: dict) -> dict:
    return {
        'id':                 row['id'],
        'conversation_id':    row.get('conversation_id') or '',
        'patient_id':         row['patient_id'],
        'medecin_id':         row['medecin_id'],
        'sender_role':        row.get('sender_role') or 'medecin',
        'rdv_id':             row.get('rdv_id') or '',
        'contenu':            _dec(row.get('contenu') or ''),
        'has_audio':          bool((row.get('audio_path') or '').strip()),
        'audio_duration_sec': int(row.get('audio_duration_sec') or 0),
        'date':               row.get('date') or '',
        'lu':                 bool(row.get('lu')),
    }


def _fmt_conv(row: dict) -> dict:
    return {
        'id':              row['id'],
        'patient_id':      row['patient_id'],
        'medecin_id':      row['medecin_id'],
        'subject':         _dec(row.get('subject') or ''),
        'status':          row.get('status') or 'open',
        'created_at':      row.get('created_at') or '',
        'last_message_at': row.get('last_message_at') or '',
        'closed_at':       row.get('closed_at') or '',
        'closed_by':       row.get('closed_by') or '',
    }


def _primary_medecin_for_patient(db, pid: str) -> str | None:
    """Pick the doctor a patient should message: assigned medecin_id, else most recent RDV/doctor link."""
    row = db.execute("SELECT medecin_id FROM patients WHERE id=?", (pid,)).fetchone()
    if row and row['medecin_id']:
        return row['medecin_id']
    row = db.execute(
        "SELECT medecin_id FROM patient_doctors WHERE patient_id=? ORDER BY created_at DESC LIMIT 1",
        (pid,)
    ).fetchone()
    if row:
        return row['medecin_id']
    row = db.execute(
        "SELECT medecin_id FROM rdv WHERE patient_id=? AND medecin_id!='' ORDER BY date DESC LIMIT 1",
        (pid,)
    ).fetchone()
    return row['medecin_id'] if row else None


def _get_or_open_conversation(db, pid: str, medecin_id: str, subject_seed: str) -> str:
    """Return the id of the most recent open conversation between pid/medecin_id, or create one."""
    row = db.execute(
        "SELECT id FROM conversations WHERE patient_id=? AND medecin_id=? AND status='open' "
        "ORDER BY last_message_at DESC LIMIT 1",
        (pid, medecin_id)
    ).fetchone()
    if row:
        return row['id']
    cid = "CONV" + str(uuid.uuid4())[:6].upper()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    snippet = (subject_seed or '').strip()[:120]
    db.execute(
        "INSERT INTO conversations (id,patient_id,medecin_id,subject,status,created_at,last_message_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (cid, pid, medecin_id, _enc(snippet), 'open', now, now)
    )
    return cid


def _insert_message(db, *, mid, cid, pid, medecin_id, sender_role,
                    contenu='', audio_path='', audio_duration_sec=0, rdv_id=''):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    db.execute(
        "INSERT INTO messages "
        "(id,patient_id,medecin_id,rdv_id,contenu,date,lu,deleted,"
        " conversation_id,sender_role,audio_path,audio_duration_sec) "
        "VALUES (?,?,?,?,?,?,0,0,?,?,?,?)",
        (mid, pid, medecin_id, rdv_id, _enc(contenu), now,
         cid, sender_role, audio_path, int(audio_duration_sec or 0))
    )
    db.execute("UPDATE conversations SET last_message_at=? WHERE id=?", (now, cid))
    return now


def _parse_message_payload():
    """Accept either multipart (with optional audio file) or JSON. Returns (contenu, audio_bytes, duration, rdv_id, error_tuple_or_None)."""
    contenu = ''
    audio_bytes = b''
    duration = 0
    rdv_id = ''

    if request.content_type and request.content_type.startswith('multipart/'):
        contenu = (request.form.get('contenu') or '').strip()
        rdv_id = (request.form.get('rdv_id') or '').strip()
        try:
            duration = int(request.form.get('audio_duration_sec') or 0)
        except ValueError:
            duration = 0
        f = request.files.get('audio')
        if f is not None:
            audio_bytes = f.read()
    else:
        data = request.get_json(silent=True) or {}
        contenu = (data.get('contenu') or '').strip()
        rdv_id = (data.get('rdv_id') or '').strip()

    if audio_bytes:
        if len(audio_bytes) > _AUDIO_MAX_BYTES:
            return contenu, b'', 0, rdv_id, (
                jsonify({"error": "Fichier audio trop volumineux"}), 413
            )
        if _detect_audio_mime(audio_bytes[:32]) is None:
            return contenu, b'', 0, rdv_id, (
                jsonify({"error": "Format audio non supporté"}), 400
            )
        if duration < 0 or duration > _AUDIO_MAX_SECONDS:
            duration = min(max(duration, 0), _AUDIO_MAX_SECONDS)

    if not contenu and not audio_bytes:
        return contenu, b'', 0, rdv_id, (
            jsonify({"error": "Le message ne peut pas être vide"}), 400
        )

    return contenu, audio_bytes, duration, rdv_id, None


def _email_message_async(app, to_address, prenom, nom, contenu, doctor_name, rdv_info):
    def _run():
        try:
            from email_notif import send_message_email
            host = app.config.get('APP_HOST', '')
            send_message_email(to_address, prenom, nom, contenu, doctor_name, rdv_info, host)
        except Exception as e:
            logger.error(f"send_message_email failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


# ─── DOCTOR → PATIENT: send message (text and/or audio) ──────────────────────
@bp.route('/api/patients/<pid>/messages', methods=['POST'])
def send_message(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403

    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    p_row = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not p_row:
        return jsonify({"error": "Patient non trouvé"}), 404
    p = decrypt_patient(dict(p_row))

    contenu, audio_bytes, duration, rdv_id, err = _parse_message_payload()
    if err:
        return err

    cid = _get_or_open_conversation(db, pid, u['id'], contenu or 'Message vocal')
    mid = "MSG" + str(uuid.uuid4())[:6].upper()
    audio_path = _save_audio_file(mid, audio_bytes) if audio_bytes else ''
    now = _insert_message(
        db, mid=mid, cid=cid, pid=pid, medecin_id=u['id'], sender_role='medecin',
        contenu=contenu, audio_path=audio_path, audio_duration_sec=duration, rdv_id=rdv_id
    )

    doctor_label = f"Dr. {u.get('prenom','')} {u.get('nom','')}".strip()
    add_notif(db, "message_medecin",
              f"✉ Message de {doctor_label}",
              "medecin", pid,
              {"message_id": mid, "conversation_id": cid, "has_audio": bool(audio_path)},
              medecin_id=u['id'],
              commit=False)
    db.commit()

    patient_email = p.get('email', '')
    if patient_email and '@' in patient_email:
        rdv_info = None
        if rdv_id:
            rdv_row = db.execute(
                "SELECT date, heure, type FROM rdv WHERE id=?", (rdv_id,)
            ).fetchone()
            if rdv_row:
                rdv_info = dict(rdv_row)
        email_body = contenu or "🎤 Vous avez reçu un message vocal. Connectez-vous pour l'écouter."
        _email_message_async(
            current_app._get_current_object(),
            patient_email,
            p.get('prenom', ''), p.get('nom', ''),
            email_body, doctor_label, rdv_info
        )

    return jsonify({
        "ok": True,
        "message": {
            "id": mid, "conversation_id": cid, "patient_id": pid,
            "medecin_id": u['id'], "sender_role": 'medecin',
            "rdv_id": rdv_id, "contenu": contenu,
            "has_audio": bool(audio_path),
            "audio_duration_sec": duration,
            "date": now, "lu": False
        }
    })


# ─── PATIENT → DOCTOR: send message (text and/or audio) ──────────────────────
@bp.route('/api/patients/<pid>/messages/patient', methods=['POST'])
def patient_send_message(pid):
    u = current_user()
    if not u or u['role'] != 'patient' or u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()

    contenu, audio_bytes, duration, rdv_id, err = _parse_message_payload()
    if err:
        return err

    start_new = False
    if request.content_type and request.content_type.startswith('multipart/'):
        start_new = (request.form.get('new_conversation') or '') in ('1', 'true', 'yes')
    else:
        data = request.get_json(silent=True) or {}
        start_new = bool(data.get('new_conversation'))

    medecin_id = _primary_medecin_for_patient(db, pid)
    if not medecin_id:
        return jsonify({"error": "Aucun médecin associé à votre compte."}), 400

    if start_new:
        cid = "CONV" + str(uuid.uuid4())[:6].upper()
        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        snippet = (contenu or 'Message vocal').strip()[:120]
        db.execute(
            "INSERT INTO conversations (id,patient_id,medecin_id,subject,status,created_at,last_message_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (cid, pid, medecin_id, _enc(snippet), 'open', now_ts, now_ts)
        )
    else:
        cid = _get_or_open_conversation(db, pid, medecin_id, contenu or 'Message vocal')

    mid = "MSG" + str(uuid.uuid4())[:6].upper()
    audio_path = _save_audio_file(mid, audio_bytes) if audio_bytes else ''
    now = _insert_message(
        db, mid=mid, cid=cid, pid=pid, medecin_id=medecin_id, sender_role='patient',
        contenu=contenu, audio_path=audio_path, audio_duration_sec=duration, rdv_id=rdv_id
    )

    p_row = db.execute("SELECT nom, prenom FROM patients WHERE id=?", (pid,)).fetchone()
    p = decrypt_patient(dict(p_row)) if p_row else {}
    patient_label = f"{p.get('prenom','')} {p.get('nom','')}".strip() or 'Patient'
    add_notif(db, "message_patient",
              f"✉ Message de {patient_label}",
              "patient", pid,
              {"message_id": mid, "conversation_id": cid, "has_audio": bool(audio_path)},
              medecin_id=medecin_id,
              commit=False)
    db.commit()

    return jsonify({
        "ok": True,
        "message": {
            "id": mid, "conversation_id": cid, "patient_id": pid,
            "medecin_id": medecin_id, "sender_role": 'patient',
            "rdv_id": rdv_id, "contenu": contenu,
            "has_audio": bool(audio_path),
            "audio_duration_sec": duration,
            "date": now, "lu": False
        }
    })


# ─── LIST CONVERSATIONS ──────────────────────────────────────────────────────
@bp.route('/api/patients/<pid>/conversations', methods=['GET'])
def list_conversations(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403

    rows = db.execute(
        "SELECT * FROM conversations WHERE patient_id=? "
        "ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, last_message_at DESC",
        (pid,)
    ).fetchall()

    result = []
    for row in rows:
        conv = _fmt_conv(dict(row))
        # enrich with doctor name + unread count (for the current viewer)
        doc = db.execute("SELECT nom, prenom FROM users WHERE id=?", (conv['medecin_id'],)).fetchone()
        conv['medecin_nom'] = f"Dr. {doc['prenom']} {doc['nom']}" if doc else 'Médecin'
        # unread: messages not sent by viewer and lu=0
        other_role = 'medecin' if u['role'] == 'patient' else 'patient'
        ur = db.execute(
            "SELECT COUNT(*) AS n FROM messages "
            "WHERE conversation_id=? AND deleted=0 AND lu=0 AND sender_role=?",
            (conv['id'], other_role)
        ).fetchone()
        conv['unread'] = int(ur['n']) if ur else 0
        # last message preview
        last = db.execute(
            "SELECT contenu, audio_path, sender_role, date FROM messages "
            "WHERE conversation_id=? AND deleted=0 ORDER BY date DESC LIMIT 1",
            (conv['id'],)
        ).fetchone()
        if last:
            has_audio = bool((last['audio_path'] or '').strip())
            preview_text = _dec(last['contenu'] or '')
            conv['last_preview'] = (
                preview_text[:80] if preview_text
                else ('🎤 Message vocal' if has_audio else '')
            )
            conv['last_sender_role'] = last['sender_role'] or 'medecin'
        else:
            conv['last_preview'] = ''
            conv['last_sender_role'] = ''
        result.append(conv)
    return jsonify(result)


# ─── LIST MESSAGES IN A CONVERSATION ─────────────────────────────────────────
@bp.route('/api/conversations/<cid>/messages', methods=['GET'])
def list_conversation_messages(cid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()
    conv = db.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    if not conv:
        return jsonify({"error": "Conversation non trouvée"}), 404
    if u['role'] == 'patient' and u.get('patient_id') != conv['patient_id']:
        return jsonify({"error": "Accès refusé"}), 403
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], conv['patient_id']):
        return jsonify({"error": "Accès refusé"}), 403

    rows = db.execute(
        "SELECT * FROM messages WHERE conversation_id=? AND deleted=0 ORDER BY date ASC", (cid,)
    ).fetchall()
    out = [_fmt_msg(dict(r)) for r in rows]

    # Mark messages sent by the other party as read
    other_role = 'medecin' if u['role'] == 'patient' else 'patient'
    db.execute(
        "UPDATE messages SET lu=1 WHERE conversation_id=? AND sender_role=? AND lu=0",
        (cid, other_role)
    )
    db.commit()

    # Attach doctor/patient display names
    doc = db.execute("SELECT nom, prenom FROM users WHERE id=?", (conv['medecin_id'],)).fetchone()
    medecin_nom = f"Dr. {doc['prenom']} {doc['nom']}" if doc else 'Médecin'
    p_row = db.execute("SELECT nom, prenom FROM patients WHERE id=?", (conv['patient_id'],)).fetchone()
    p = decrypt_patient(dict(p_row)) if p_row else {}
    patient_nom = f"{p.get('prenom','')} {p.get('nom','')}".strip() or 'Patient'

    return jsonify({
        "conversation": {**_fmt_conv(dict(conv)), "medecin_nom": medecin_nom, "patient_nom": patient_nom},
        "messages": out,
    })


# ─── CLOSE CONVERSATION (doctor only) ────────────────────────────────────────
@bp.route('/api/conversations/<cid>/close', methods=['POST'])
def close_conversation(cid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    conv = db.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    if not conv:
        return jsonify({"error": "Conversation non trouvée"}), 404
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], conv['patient_id']):
        return jsonify({"error": "Accès refusé"}), 403

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    db.execute(
        "UPDATE conversations SET status='closed', closed_at=?, closed_by=? WHERE id=?",
        (now, u['id'], cid)
    )
    db.commit()
    return jsonify({"ok": True, "status": "closed", "closed_at": now})


# ─── STREAM AUDIO ────────────────────────────────────────────────────────────
@bp.route('/api/messages/<mid>/audio', methods=['GET'])
def get_message_audio(mid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    row = db.execute(
        "SELECT patient_id, audio_path FROM messages WHERE id=? AND deleted=0", (mid,)
    ).fetchone()
    if not row or not (row['audio_path'] or '').strip():
        return jsonify({"error": "Audio non trouvé"}), 404
    if u['role'] == 'patient' and u.get('patient_id') != row['patient_id']:
        return jsonify({"error": "Accès refusé"}), 403
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], row['patient_id']):
        return jsonify({"error": "Accès refusé"}), 403

    path = row['audio_path']
    if not os.path.exists(path):
        return jsonify({"error": "Fichier audio manquant"}), 404
    try:
        raw = _load_audio_bytes(path)
    except Exception as e:
        logger.warning("audio decrypt failed for %s: %s", mid, e)
        return jsonify({"error": "Lecture audio impossible"}), 500

    mime = _detect_audio_mime(raw[:32]) or 'audio/webm'
    return Response(raw, mimetype=mime, headers={
        "Cache-Control": "private, max-age=0, no-store",
        "Content-Length": str(len(raw)),
    })


# ─── MARK AS READ ────────────────────────────────────────────────────────────
@bp.route('/api/messages/<mid>/lu', methods=['POST'])
def mark_message_lu(mid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    if u['role'] == 'patient':
        db.execute(
            "UPDATE messages SET lu=1 WHERE id=? AND patient_id=?",
            (mid, u.get('patient_id'))
        )
    elif u['role'] == 'medecin':
        msg_row = db.execute("SELECT patient_id FROM messages WHERE id=?", (mid,)).fetchone()
        if not msg_row:
            return jsonify({"error": "Message non trouvé"}), 404
        if not medecin_can_access_patient(db, u['id'], msg_row['patient_id']):
            return jsonify({"error": "Accès refusé"}), 403
        db.execute("UPDATE messages SET lu=1 WHERE id=?", (mid,))
    else:
        db.execute("UPDATE messages SET lu=1 WHERE id=?", (mid,))
    db.commit()
    return jsonify({"ok": True})


# ─── DELETE MESSAGE ──────────────────────────────────────────────────────────
@bp.route('/api/messages/<mid>', methods=['DELETE'])
def delete_message(mid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    if u['role'] == 'patient':
        row = db.execute(
            "SELECT id, lu, audio_path, sender_role FROM messages "
            "WHERE id=? AND patient_id=? AND deleted=0",
            (mid, u.get('patient_id'))
        ).fetchone()
        if not row:
            return jsonify({"error": "Message non trouvé"}), 404
        # Patient can freely delete their own messages; for doctor messages, require read first.
        if row['sender_role'] == 'medecin' and not row['lu']:
            return jsonify({"error": "Veuillez d'abord marquer le message comme lu"}), 400
    else:
        row = db.execute(
            "SELECT id, patient_id, audio_path FROM messages WHERE id=? AND deleted=0", (mid,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Message non trouvé"}), 404
        if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], row['patient_id']):
            return jsonify({"error": "Accès refusé"}), 403

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    db.execute("UPDATE messages SET deleted=1, deleted_at=? WHERE id=?", (now, mid))
    db.commit()

    # Best-effort remove audio file
    audio_path = (row['audio_path'] or '').strip() if 'audio_path' in row.keys() else ''
    if audio_path and os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except OSError:
            pass

    return jsonify({"ok": True})


# ─── LEGACY FLAT LIST (kept for backward compatibility) ──────────────────────
@bp.route('/api/patients/<pid>/messages', methods=['GET'])
def get_messages(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403

    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    rows = db.execute(
        "SELECT * FROM messages WHERE patient_id=? AND deleted=0 ORDER BY date DESC", (pid,)
    ).fetchall()

    result = []
    for row in rows:
        m = _fmt_msg(dict(row))
        if m['rdv_id']:
            rdv_row = db.execute(
                "SELECT date, heure, type FROM rdv WHERE id=?", (m['rdv_id'],)
            ).fetchone()
            if rdv_row:
                m['rdv_info'] = dict(rdv_row)
        doc_row = db.execute(
            "SELECT nom, prenom FROM users WHERE id=?", (m['medecin_id'],)
        ).fetchone()
        m['medecin_nom'] = f"Dr. {doc_row['prenom']} {doc_row['nom']}" if doc_row else ''
        result.append(m)
    return jsonify(result)
