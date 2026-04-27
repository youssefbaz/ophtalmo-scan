"""Shared audio upload + storage helpers for message / question voice recordings."""
import os
import base64
import datetime
import logging
from flask import request

from security_utils import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)

AUDIO_RETENTION_DAYS = 92


AUDIO_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'uploads'
)
AUDIO_MAX_BYTES = 8 * 1024 * 1024
AUDIO_MAX_SECONDS = 180

# (magic_bytes, mime, offset)
_ALLOWED_AUDIO_MAGIC = [
    (b'\x1aE\xdf\xa3',  'audio/webm', 0),
    (b'OggS',           'audio/ogg',  0),
    (b'ID3',            'audio/mpeg', 0),
    (b'\xff\xfb',       'audio/mpeg', 0),
    (b'\xff\xf3',       'audio/mpeg', 0),
    (b'\xff\xf2',       'audio/mpeg', 0),
    # iOS Safari MediaRecorder outputs audio/mp4 (ISO BMFF: "ftyp" at offset 4)
    (b'ftyp',           'audio/mp4',  4),
]


def detect_audio_mime(raw: bytes) -> str | None:
    for magic, mime, off in _ALLOWED_AUDIO_MAGIC:
        if raw[off:off + len(magic)] == magic:
            return mime
    return None


def save_audio(subdir: str, record_id: str, raw_bytes: bytes) -> str:
    out_dir = os.path.join(AUDIO_ROOT, subdir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{record_id}.enc")
    payload_b64 = base64.b64encode(raw_bytes).decode('ascii')
    encrypted = encrypt_field(payload_b64)
    with open(path, 'w', encoding='ascii') as f:
        f.write(encrypted)
    return path


def load_audio(path: str) -> bytes:
    with open(path, 'r', encoding='ascii') as f:
        encrypted = f.read().strip()
    return base64.b64decode(decrypt_field(encrypted))


def read_audio_from_request(field: str = 'audio', duration_field: str = 'audio_duration_sec'):
    """Extract (bytes, duration_sec, error) from a multipart request. Returns (b'', 0, None) if no audio present."""
    if not (request.content_type and request.content_type.startswith('multipart/')):
        return b'', 0, None
    f = request.files.get(field)
    if f is None:
        return b'', 0, None
    raw = f.read()
    if not raw:
        return b'', 0, None
    if len(raw) > AUDIO_MAX_BYTES:
        return b'', 0, ("Fichier audio trop volumineux", 413)
    if detect_audio_mime(raw[:32]) is None:
        return b'', 0, ("Format audio non supporté", 400)
    try:
        duration = int(request.form.get(duration_field) or 0)
    except ValueError:
        duration = 0
    duration = max(0, min(duration, AUDIO_MAX_SECONDS))
    return raw, duration, None


def _unlink_safe(path: str) -> bool:
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError as e:
        logger.warning("Audio prune: failed to remove %s: %s", path, e)
        return False


def prune_old_audio(app, retention_days: int = AUDIO_RETENTION_DAYS) -> dict:
    """Delete encrypted audio files older than `retention_days` days and clear
    their DB references. Text content of messages/questions is preserved.

    Compares against the stored creation date of the parent record. The date
    column is a TEXT timestamp formatted as "YYYY-MM-DD HH:MM:SS.ffffff" — text
    comparison against the cutoff prefix is correct because the format sorts
    lexicographically.

    Returns a counters dict; safe to call from the daily scheduler.
    """
    from database import get_db

    cutoff = (datetime.datetime.now() - datetime.timedelta(days=retention_days)) \
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    counters = {"messages": 0, "questions_q": 0, "questions_r": 0, "errors": 0}

    with app.app_context():
        db = get_db()

        # Messages: single audio_path per row
        rows = db.execute(
            "SELECT id, audio_path FROM messages "
            "WHERE audio_path != '' AND date != '' AND date < ?",
            (cutoff,)
        ).fetchall()
        for row in rows:
            if _unlink_safe(row['audio_path']):
                db.execute(
                    "UPDATE messages SET audio_path='', audio_duration_sec=0 WHERE id=?",
                    (row['id'],)
                )
                counters["messages"] += 1
            else:
                counters["errors"] += 1

        # Questions: question audio (uses date) and reponse audio (uses date_reponse)
        q_rows = db.execute(
            "SELECT id, question_audio_path FROM questions "
            "WHERE question_audio_path != '' AND date != '' AND date < ?",
            (cutoff,)
        ).fetchall()
        for row in q_rows:
            if _unlink_safe(row['question_audio_path']):
                db.execute(
                    "UPDATE questions SET question_audio_path='', question_audio_duration=0 WHERE id=?",
                    (row['id'],)
                )
                counters["questions_q"] += 1
            else:
                counters["errors"] += 1

        r_rows = db.execute(
            "SELECT id, reponse_audio_path FROM questions "
            "WHERE reponse_audio_path != '' AND date_reponse != '' AND date_reponse < ?",
            (cutoff,)
        ).fetchall()
        for row in r_rows:
            if _unlink_safe(row['reponse_audio_path']):
                db.execute(
                    "UPDATE questions SET reponse_audio_path='', reponse_audio_duration=0 WHERE id=?",
                    (row['id'],)
                )
                counters["questions_r"] += 1
            else:
                counters["errors"] += 1

        db.commit()

    logger.info("Audio retention prune (>%dd): %s", retention_days, counters)
    return counters
