import json, uuid, datetime
from flask import Blueprint, request, jsonify
from database import get_db, current_user

bp = Blueprint('ordonnances', __name__)


@bp.route('/api/patients/<pid>/ordonnances', methods=['GET'])
def get_ordonnances(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM ordonnances WHERE patient_id=? ORDER BY date DESC", (pid,)
    ).fetchall()
    result = []
    for r in rows:
        o = dict(r)
        try:
            o['contenu'] = json.loads(o['contenu'] or '{}')
        except Exception:
            o['contenu'] = {}
        result.append(o)
    return jsonify(result)


@bp.route('/api/patients/<pid>/ordonnances', methods=['POST'])
def add_ordonnance(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    if not db.execute("SELECT id FROM patients WHERE id=?", (pid,)).fetchone():
        return jsonify({"error": "Patient non trouvé"}), 404
    oid = "O" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO ordonnances (id,patient_id,date,medecin,type,contenu,notes) "
        "VALUES (?,?,?,?,?,?,?)",
        (oid, pid,
         data.get('date', datetime.date.today().isoformat()),
         u['nom'],
         data.get('type', 'medicaments'),
         json.dumps(data.get('contenu', {})),
         data.get('notes', ''))
    )
    db.commit()
    return jsonify({"ok": True, "id": oid}), 201


@bp.route('/api/patients/<pid>/ordonnances/<oid>', methods=['DELETE'])
def delete_ordonnance(pid, oid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute("DELETE FROM ordonnances WHERE id=? AND patient_id=?", (oid, pid))
    db.commit()
    return jsonify({"ok": True})
