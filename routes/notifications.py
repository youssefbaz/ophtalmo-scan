import json
from flask import Blueprint, jsonify
from database import get_db, current_user

bp = Blueprint('notifications', __name__)


@bp.route('/api/notifications', methods=['GET'])
def get_notifications():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()

    if u['role'] == 'medecin':
        rows = db.execute(
            "SELECT * FROM notifications ORDER BY date DESC LIMIT 20"
        ).fetchall()
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
        try:
            n['data'] = json.loads(n.get('data') or '{}')
        except Exception:
            n['data'] = {}
        result.append(n)
    return jsonify(result)


@bp.route('/api/notifications/<nid>/lu', methods=['POST'])
def mark_lu(nid):
    db = get_db()
    db.execute("UPDATE notifications SET lu=1 WHERE id=?", (nid,))
    db.commit()
    return jsonify({"ok": True})
