import re, json
from flask import Blueprint, jsonify
from database import get_db, current_user
from security_utils import decrypt_field

bp = Blueprint('notifications', __name__)

# Fernet tokens are base64url strings starting with gAAAAA (version byte 0x80)
_FERNET_RE = re.compile(r'gAAAAA[A-Za-z0-9_\-]{40,}={0,2}')


def _decrypt_message(msg: str) -> str:
    """Replace any embedded Fernet tokens inside a notification message with their plaintext."""
    if not msg or 'gAAAAA' not in msg:
        return msg
    def _replace(m):
        decrypted = decrypt_field(m.group(0))
        # decrypt_field returns the original string on failure, so this is safe
        return decrypted
    return _FERNET_RE.sub(_replace, msg)


@bp.route('/api/notifications', methods=['GET'])
def get_notifications():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()

    if u['role'] == 'medecin':
        # Show notifications:
        #   1. Explicitly targeted at this doctor (medecin_id = me)
        #   2. From patients in this doctor's roster (patient_id IN my patients)
        #   3. System-wide broadcasts (no patient_id, no medecin_id) but NOT admin actions
        # Exclude anything sent by 'admin' with no patient — those are admin-only events
        rows = db.execute("""
            SELECT n.* FROM notifications n
            WHERE n.medecin_id = ?
               OR n.patient_id IN (
                   SELECT id FROM patients WHERE medecin_id = ?
               )
               OR (
                   (n.patient_id IS NULL OR n.patient_id = '')
                   AND (n.medecin_id IS NULL OR n.medecin_id = '')
                   AND n.from_role != 'admin'
               )
            ORDER BY n.date DESC LIMIT 30
        """, (u['id'], u['id'])).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM notifications WHERE patient_id=? AND from_role='medecin' "
            "ORDER BY date DESC LIMIT 10",
            (u.get('patient_id'),)
        ).fetchall()

    result = []
    for row in rows:
        n = dict(row)
        n['lu'] = bool(n['lu'])
        n['message'] = _decrypt_message(n.get('message') or '')
        try:
            n['data'] = json.loads(n.get('data') or '{}')
        except Exception:
            n['data'] = {}
        result.append(n)
    return jsonify(result)


@bp.route('/api/notifications/<nid>/lu', methods=['POST'])
def mark_lu(nid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    db.execute("UPDATE notifications SET lu=1 WHERE id=?", (nid,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/notifications', methods=['DELETE'])
def clear_notifications():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute("DELETE FROM notifications")
    db.commit()
    return jsonify({"ok": True})
