import uuid, datetime, threading, logging
from flask import Blueprint, request, jsonify, current_app
from database import get_db, current_user, add_notif
from security_utils import encrypt_field, decrypt_field, decrypt_patient

logger = logging.getLogger(__name__)

bp = Blueprint('messages', __name__)


def _enc(text: str) -> str:
    return encrypt_field(text) if text else ''


def _dec(text: str) -> str:
    return decrypt_field(text) if text else ''


def _fmt_msg(row: dict) -> dict:
    return {
        'id':         row['id'],
        'patient_id': row['patient_id'],
        'medecin_id': row['medecin_id'],
        'rdv_id':     row.get('rdv_id') or '',
        'contenu':    _dec(row.get('contenu') or ''),
        'date':       row.get('date') or '',
        'lu':         bool(row.get('lu')),
        'rdv_info':   None,  # enriched below when needed
    }


def _send_email_async(app, to_address, prenom, nom, contenu, doctor_name, rdv_info):
    """Fire-and-forget email in a background thread."""
    def _run():
        try:
            from email_notif import send_message_email
            host = app.config.get('APP_HOST', '')
            send_message_email(to_address, prenom, nom, contenu, doctor_name, rdv_info, host)
        except Exception as e:
            logger.error(f"send_message_email failed: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ─── SEND MESSAGE (doctor → patient) ─────────────────────────────────────────
@bp.route('/api/patients/<pid>/messages', methods=['POST'])
def send_message(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403

    db = get_db()
    p_row = db.execute("SELECT * FROM patients WHERE id=? AND deleted=0", (pid,)).fetchone()
    if not p_row:
        return jsonify({"error": "Patient non trouvé"}), 404
    p = decrypt_patient(dict(p_row))

    data    = request.json or {}
    contenu = (data.get('contenu') or '').strip()
    rdv_id  = (data.get('rdv_id') or '').strip()
    if not contenu:
        return jsonify({"error": "Le message ne peut pas être vide"}), 400

    mid = "MSG" + str(uuid.uuid4())[:6].upper()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO messages (id,patient_id,medecin_id,rdv_id,contenu,date,lu,deleted) "
        "VALUES (?,?,?,?,?,?,0,0)",
        (mid, pid, u['id'], rdv_id, _enc(contenu), now)
    )

    # In-app notification for the patient
    doctor_label = f"Dr. {u.get('prenom','')} {u.get('nom','')}".strip()
    add_notif(db, "message_medecin",
              f"✉ Message de {doctor_label}",
              "medecin", pid,
              {"message_id": mid},
              medecin_id=u['id'],
              commit=False)
    db.commit()

    # Email notification (fire and forget)
    patient_email = p.get('email', '')
    if patient_email and '@' in patient_email:
        rdv_info = None
        if rdv_id:
            rdv_row = db.execute(
                "SELECT date, heure, type FROM rdv WHERE id=?", (rdv_id,)
            ).fetchone()
            if rdv_row:
                rdv_info = dict(rdv_row)
        _send_email_async(
            current_app._get_current_object(),
            patient_email,
            p.get('prenom', ''), p.get('nom', ''),
            contenu, doctor_label, rdv_info
        )

    return jsonify({
        "ok": True,
        "message": {
            "id": mid, "patient_id": pid, "medecin_id": u['id'],
            "rdv_id": rdv_id, "contenu": contenu, "date": now, "lu": False
        }
    })


# ─── GET MESSAGES ─────────────────────────────────────────────────────────────
@bp.route('/api/patients/<pid>/messages', methods=['GET'])
def get_messages(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403

    db = get_db()
    rows = db.execute(
        "SELECT * FROM messages WHERE patient_id=? AND deleted=0 ORDER BY date DESC", (pid,)
    ).fetchall()

    result = []
    for row in rows:
        m = _fmt_msg(dict(row))
        # Enrich with RDV info if linked
        if m['rdv_id']:
            rdv_row = db.execute(
                "SELECT date, heure, type FROM rdv WHERE id=?", (m['rdv_id'],)
            ).fetchone()
            if rdv_row:
                m['rdv_info'] = dict(rdv_row)
        # Enrich with doctor name
        doc_row = db.execute(
            "SELECT nom, prenom FROM users WHERE id=?", (m['medecin_id'],)
        ).fetchone()
        m['medecin_nom'] = f"Dr. {doc_row['prenom']} {doc_row['nom']}" if doc_row else ''
        result.append(m)

    return jsonify(result)


# ─── MARK AS READ ─────────────────────────────────────────────────────────────
@bp.route('/api/messages/<mid>/lu', methods=['POST'])
def mark_message_lu(mid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    # Patient can only mark their own messages
    if u['role'] == 'patient':
        db.execute(
            "UPDATE messages SET lu=1 WHERE id=? AND patient_id=?",
            (mid, u.get('patient_id'))
        )
    else:
        db.execute("UPDATE messages SET lu=1 WHERE id=?", (mid,))
    db.commit()
    return jsonify({"ok": True})


# ─── DELETE MESSAGE (patient deletes a read message) ─────────────────────────
@bp.route('/api/messages/<mid>', methods=['DELETE'])
def delete_message(mid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    if u['role'] == 'patient':
        row = db.execute(
            "SELECT id, lu FROM messages WHERE id=? AND patient_id=? AND deleted=0",
            (mid, u.get('patient_id'))
        ).fetchone()
        if not row:
            return jsonify({"error": "Message non trouvé"}), 404
        if not row['lu']:
            return jsonify({"error": "Veuillez d'abord marquer le message comme lu"}), 400
    else:
        row = db.execute(
            "SELECT id FROM messages WHERE id=? AND deleted=0", (mid,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Message non trouvé"}), 404

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "UPDATE messages SET deleted=1, deleted_at=? WHERE id=?", (now, mid)
    )
    db.commit()
    return jsonify({"ok": True})
