"""Shared audio upload + storage helpers for message / question voice recordings."""
import os
import base64
from flask import request

from security_utils import encrypt_field, decrypt_field


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
