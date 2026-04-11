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
        # Only show notifications for this doctor's own patients (+ system-wide ones)
        rows = db.execute("""
            SELECT n.* FROM notifications n
            WHERE n.patient_id IS NULL
               OR n.patient_id = ''
               OR n.patient_id IN (
                   SELECT id FROM patients WHERE medecin_id = ?
               )
            ORDER BY n.date DESC LIMIT 30
        """, (u['id'],)).fetchall()
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
