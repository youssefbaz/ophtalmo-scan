"""
routes/totp.py — TOTP 2FA management endpoints (Step 3).

Endpoints:
  POST /api/totp/setup    — generate a new TOTP secret + QR code + backup codes
  POST /api/totp/verify   — confirm the TOTP code and activate 2FA
  POST /api/totp/disable  — disable 2FA (requires current password + TOTP code)
"""
import io
import uuid
import base64
import hashlib
import secrets
import pyotp
import qrcode
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from database import get_db, current_user, log_audit
from security_utils import get_client_ip, get_user_agent

bp = Blueprint('totp', __name__)

_ISSUER = "OphtalmoScan"


def _generate_backup_codes(db, user_id: str) -> list:
    """Generate 8 one-time backup codes, store hashed, return plaintext formatted strings."""
    # Invalidate any previous unused codes for this user
    db.execute("DELETE FROM totp_backup_codes WHERE user_id=? AND used=0", (user_id,))
    codes = []
    for _ in range(8):
        raw = secrets.token_hex(4).upper()          # 8-char hex  e.g. "A3F29E1B"
        display = f"{raw[:4]}-{raw[4:]}"            # "A3F2-9E1B"
        code_hash = hashlib.sha256(raw.encode()).hexdigest()
        db.execute(
            "INSERT INTO totp_backup_codes (id, user_id, code_hash, used) VALUES (?,?,?,0)",
            (str(uuid.uuid4())[:8], user_id, code_hash)
        )
        codes.append(display)
    return codes


@bp.route('/api/totp/setup', methods=['POST'])
def totp_setup():
    """Generate a new TOTP secret, QR code and backup codes for the logged-in user."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (u['id'],)).fetchone()

    # If 2FA is already active, refuse re-setup without disabling first
    if row['totp_enabled']:
        return jsonify({"error": "La 2FA est déjà activée. Désactivez-la d'abord."}), 409

    # Generate a fresh secret every time setup is called
    secret = pyotp.random_base32()

    # Build the OTP auth URL for QR code
    label    = f"{u['nom']} {u.get('prenom', '')}".strip()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=label, issuer_name=_ISSUER
    )

    # Render QR code to PNG → base64
    qr_img = qrcode.make(totp_uri)
    buf    = io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Persist the (not-yet-activated) secret
    db.execute("UPDATE users SET totp_secret=?, totp_enabled=0 WHERE id=?",
               (secret, u['id']))

    # Generate backup codes (stored hashed, returned once in plaintext)
    backup_codes = _generate_backup_codes(db, u['id'])
    db.commit()

    return jsonify({
        "ok":           True,
        "secret":       secret,
        "qr":           f"data:image/png;base64,{qr_b64}",
        "uri":          totp_uri,
        "backup_codes": backup_codes,
    })


@bp.route('/api/totp/verify', methods=['POST'])
def totp_verify():
    """Activate 2FA by verifying the first TOTP code."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    data  = request.json or {}
    token = data.get('token', '').strip()

    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (u['id'],)).fetchone()

    if not row['totp_secret']:
        return jsonify({"error": "Aucun secret 2FA trouvé. Lancez d'abord /api/totp/setup."}), 400
    if row['totp_enabled']:
        return jsonify({"error": "La 2FA est déjà activée."}), 409

    totp = pyotp.TOTP(row['totp_secret'])
    if not totp.verify(token, valid_window=1):
        return jsonify({"error": "Code invalide. Vérifiez l'heure de votre appareil et réessayez."}), 400

    db.execute("UPDATE users SET totp_enabled=1 WHERE id=?", (u['id'],))
    log_audit(db, 'totp_enabled', u['id'], '', ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True, "message": "Authentification à deux facteurs activée avec succès."})


@bp.route('/api/totp/disable', methods=['POST'])
def totp_disable():
    """Disable 2FA — requires current password confirmation."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    data     = request.json or {}
    password = data.get('password', '')
    token    = data.get('token', '').strip()

    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (u['id'],)).fetchone()

    if not row['totp_enabled']:
        return jsonify({"error": "La 2FA n'est pas activée."}), 400

    # Require both password and current TOTP code
    if not check_password_hash(row['password_hash'], password):
        return jsonify({"error": "Mot de passe incorrect"}), 401

    totp = pyotp.TOTP(row['totp_secret'])
    if not totp.verify(token, valid_window=1):
        return jsonify({"error": "Code 2FA invalide"}), 401

    db.execute("UPDATE users SET totp_secret='', totp_enabled=0 WHERE id=?", (u['id'],))
    # Invalidate all backup codes
    db.execute("DELETE FROM totp_backup_codes WHERE user_id=?", (u['id'],))
    log_audit(db, 'totp_disabled', u['id'], '', ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True, "message": "Authentification à deux facteurs désactivée."})


@bp.route('/api/totp/backup-codes', methods=['GET'])
def list_backup_codes():
    """Return how many unused backup codes the user still has (count only, not codes)."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM totp_backup_codes WHERE user_id=? AND used=0", (u['id'],)
    ).fetchone()
    return jsonify({"remaining": row['cnt'] if row else 0})
