"""
routes/patients_surgery.py — Surgery scheduling and post-op follow-up endpoints.
"""
import uuid, datetime, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif
from security_utils import decrypt_patient
from routes.patients_helpers import _generate_suivi, SUIVI_ETAPES

logger = logging.getLogger(__name__)

bp = Blueprint('patients_surgery', __name__)


@bp.route('/api/patients/<pid>/chirurgie', methods=['POST'])
def set_chirurgie(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    db.execute(
        "UPDATE patients SET date_chirurgie=?, type_chirurgie=? WHERE id=?",
        (data.get('date_chirurgie',''), data.get('type_chirurgie',''), pid)
    )
    db.commit()
    date_chir   = data.get('date_chirurgie', '')
    type_chir   = data.get('type_chirurgie', '')
    medecin_nom = f"{u.get('prenom','')} {u.get('nom','')}".strip()
    if date_chir:
        _generate_suivi(db, pid, date_chir, medecin_nom=medecin_nom, type_chirurgie=type_chir)
    p = db.execute("SELECT prenom, nom FROM patients WHERE id=?", (pid,)).fetchone()
    if p:
        p_dec = decrypt_patient(dict(p))
        add_notif(db, "chirurgie",
                  f"✂️ Chirurgie planifiée pour {p_dec['prenom']} {p_dec['nom']} : {date_chir} — RDV post-op créés",
                  "medecin", pid)
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/chirurgie', methods=['DELETE'])
def delete_chirurgie(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # Soft-delete all linked RDVs from the agenda
    rdv_ids = [r['rdv_id'] for r in
               db.execute("SELECT rdv_id FROM suivi_postop WHERE patient_id=? AND rdv_id!=''", (pid,)).fetchall()]
    for rid in rdv_ids:
        db.execute(
            "UPDATE rdv SET deleted=1, deleted_at=? WHERE id=?", (now, rid)
        )
    # Hard-delete suivi steps (reset operation, not accidental)
    db.execute("DELETE FROM suivi_postop WHERE patient_id=?", (pid,))
    # Clear surgery fields on patient
    db.execute("UPDATE patients SET date_chirurgie='', type_chirurgie='' WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/suivi', methods=['GET'])
def get_suivi(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM suivi_postop WHERE patient_id=? ORDER BY date_prevue", (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/suivi/<sid>', methods=['PUT'])
def update_suivi(pid, sid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM suivi_postop WHERE id=? AND patient_id=?", (sid, pid)).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404

    statut        = data.get('statut',        row['statut'])
    date_reelle   = data.get('date_reelle',   row['date_reelle'])
    historique_id = data.get('historique_id', row['historique_id'])
    notes         = data.get('notes',         row['notes'])
    date_prevue   = data.get('date_prevue',   row['date_prevue'])
    heure         = data.get('heure',         None)

    db.execute(
        "UPDATE suivi_postop SET statut=?, date_reelle=?, historique_id=?, notes=?, date_prevue=? WHERE id=?",
        (statut, date_reelle, historique_id, notes, date_prevue, sid)
    )

    rdv_id = row['rdv_id']
    if rdv_id:
        if heure:
            db.execute("UPDATE rdv SET date=?, heure=? WHERE id=?", (date_prevue, heure, rdv_id))
        else:
            db.execute("UPDATE rdv SET date=? WHERE id=?", (date_prevue, rdv_id))

    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/suivi/<sid>/reset', methods=['POST'])
def reset_suivi(pid, sid):
    """Reset a step back to a_faire without deleting it."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute(
        "UPDATE suivi_postop SET statut='a_faire', date_reelle='', historique_id='', notes='' "
        "WHERE id=? AND patient_id=?",
        (sid, pid)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/suivi/<sid>', methods=['DELETE'])
def delete_suivi(pid, sid):
    """Permanently delete a suivi step and soft-delete its linked RDV."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute("SELECT rdv_id FROM suivi_postop WHERE id=? AND patient_id=?", (sid, pid)).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404
    if row['rdv_id']:
        db.execute(
            "UPDATE rdv SET deleted=1, deleted_at=? WHERE id=?",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), row['rdv_id'])
        )
    db.execute("DELETE FROM suivi_postop WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


# ─── BOOK RDV FOR A SUIVI STEP ────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/suivi/<sid>/book-rdv', methods=['POST'])
def book_suivi_rdv(pid, sid):
    """Create an agenda RDV for a suivi step that has none (rdv_id empty).
    If one already exists, return it without creating a duplicate.
    """
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()

    row = db.execute(
        "SELECT * FROM suivi_postop WHERE id=? AND patient_id=?", (sid, pid)
    ).fetchone()
    if not row:
        return jsonify({"error": "Étape de suivi introuvable"}), 404

    # Already linked — return existing
    if row['rdv_id']:
        existing = db.execute(
            "SELECT id, date, heure, statut FROM rdv WHERE id=? AND (deleted IS NULL OR deleted=0)",
            (row['rdv_id'],)
        ).fetchone()
        if existing:
            return jsonify({"ok": True, "rdv_id": existing['id'],
                            "already_exists": True, "date": existing['date'], "heure": existing['heure']})

    from security_utils import decrypt_field
    data      = request.json or {}
    heure     = data.get('heure', row['heure'] or '09:00')
    date_rdv  = data.get('date',  row['date_prevue'])
    lbl       = row['etape']

    # Resolve doctor name for the RDV
    u_row = db.execute("SELECT nom, prenom FROM users WHERE id=?", (u['id'],)).fetchone()
    medecin_nom = f"Dr. {decrypt_field(u_row['prenom'] or '') if u_row else ''} {decrypt_field(u_row['nom'] or '') if u_row else ''}".strip()

    rdv_id  = "RDV" + str(uuid.uuid4())[:6].upper()
    type_rdv = f"Contrôle post-op {lbl}"
    db.execute(
        "INSERT INTO rdv (id,patient_id,date,heure,type,statut,medecin,notes,urgent,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rdv_id, pid, date_rdv, heure, type_rdv, 'programmé',
         medecin_nom, f"Suivi post-opératoire automatique — {lbl}", 0, u['id'])
    )
    db.execute(
        "UPDATE suivi_postop SET rdv_id=? WHERE id=?", (rdv_id, sid)
    )
    db.commit()
    return jsonify({"ok": True, "rdv_id": rdv_id, "already_exists": False,
                    "date": date_rdv, "heure": heure})
