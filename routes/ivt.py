import uuid, datetime
from flask import Blueprint, request, jsonify
from database import get_db, current_user, log_audit

bp = Blueprint('ivt', __name__)

IVT_MEDICAMENTS = ["Ranibizumab", "Aflibercept", "Bevacizumab", "Faricimab", "Brolucizumab"]


@bp.route('/api/patients/<pid>/ivt', methods=['GET'])
def get_ivt(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM ivt WHERE patient_id=? AND (deleted IS NULL OR deleted=0) ORDER BY date DESC, numero DESC", (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/ivt', methods=['POST'])
def add_ivt(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if not db.execute("SELECT id FROM patients WHERE id=?", (pid,)).fetchone():
        return jsonify({"error": "Patient non trouvé"}), 404

    data = request.json or {}
    oeil       = data.get('oeil', 'OG')
    medicament = data.get('medicament', 'Ranibizumab')
    dose       = data.get('dose', '0.5mg')
    date       = data.get('date', datetime.date.today().isoformat())
    notes      = data.get('notes', '')

    # Auto-number: count previous injections for same eye
    count = db.execute(
        "SELECT COUNT(*) FROM ivt WHERE patient_id=? AND oeil=?", (pid, oeil)
    ).fetchone()[0]
    numero = count + 1

    iid = "IVT" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO ivt (id, patient_id, oeil, medicament, dose, date, numero, notes, medecin) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (iid, pid, oeil, medicament, dose, date, numero, notes, u['nom'])
    )
    db.commit()
    return jsonify({"ok": True, "id": iid, "numero": numero}), 201


@bp.route('/api/patients/<pid>/ivt/<iid>', methods=['DELETE'])
def delete_ivt(pid, iid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute(
        "SELECT oeil FROM ivt WHERE id=? AND patient_id=? AND (deleted IS NULL OR deleted=0)",
        (iid, pid)
    ).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404
    # Soft-delete: preserve the record for history/audit
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("UPDATE ivt SET deleted=1, deleted_at=? WHERE id=?", (now, iid))
    # Re-number remaining active injections for same eye
    remaining = db.execute(
        "SELECT id FROM ivt WHERE patient_id=? AND oeil=? AND (deleted IS NULL OR deleted=0) ORDER BY date, id",
        (pid, row['oeil'])
    ).fetchall()
    for i, r in enumerate(remaining, start=1):
        db.execute("UPDATE ivt SET numero=? WHERE id=?", (i, r['id']))
    log_audit(db, 'DELETE', 'ivt', iid, u['id'], pid, f"oeil={row['oeil']}")
    db.commit()
    return jsonify({"ok": True})
