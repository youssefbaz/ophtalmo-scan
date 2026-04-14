import uuid, datetime, logging, re
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif
from security_utils import decrypt_field, decrypt_patient, valid_date, valid_heure

# Detect Fernet tokens accidentally stored in plain-text fields
_FERNET_RE = re.compile(r'^gAAAAA[A-Za-z0-9_\-]{40,}={0,2}$')

def _clean_medecin(value: str) -> str:
    """Return an empty string if value looks like an encrypted Fernet token."""
    if value and _FERNET_RE.match(value.strip()):
        return ''
    return value or ''

logger = logging.getLogger(__name__)

bp = Blueprint('rdv', __name__)


@bp.route('/api/rdv', methods=['GET'])
def get_rdv():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()
    if u['role'] == 'patient':
        rows = db.execute("""
            SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom
            FROM rdv r JOIN patients p ON r.patient_id = p.id
            WHERE r.patient_id = ?
              AND (r.deleted IS NULL OR r.deleted = 0)
            ORDER BY r.date, r.heure
        """, (u.get('patient_id'),)).fetchall()
    else:
        # Show RDVs explicitly assigned to this doctor (medecin_id),
        # plus legacy RDVs for this doctor's patients (backward compat)
        rows = db.execute("""
            SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom
            FROM rdv r JOIN patients p ON r.patient_id = p.id
            WHERE (r.medecin_id = ?
               OR ((r.medecin_id IS NULL OR r.medecin_id = '') AND p.medecin_id = ?))
              AND (r.deleted IS NULL OR r.deleted = 0)
            ORDER BY r.date, r.heure
        """, (u['id'], u['id'])).fetchall()
    result = [dict(r) for r in rows]
    for r in result:
        r['urgent'] = bool(r['urgent'])
        r['patient_nom']    = decrypt_field(r.get('patient_nom', '') or '')
        r['patient_prenom'] = decrypt_field(r.get('patient_prenom', '') or '')
        r['medecin'] = _clean_medecin(r.get('medecin', '') or '')
    return jsonify(result)


@bp.route('/api/rdv', methods=['POST'])
def add_rdv():
    u = current_user()
    if not u:
        return jsonify({}), 401
    data = request.json or {}
    db = get_db()
    pid = data.get('patient_id') or u.get('patient_id')
    _p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not _p:
        return jsonify({"error": "Patient non trouvé"}), 404
    p = decrypt_patient(dict(_p))
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403

    rdv_date  = data.get('date', '')
    rdv_heure = data.get('heure', '')

    if rdv_date and not valid_date(rdv_date):
        return jsonify({"error": "Format de date invalide (YYYY-MM-DD attendu)."}), 400
    if rdv_heure and not valid_heure(rdv_heure):
        return jsonify({"error": "Format d'heure invalide (HH:MM attendu)."}), 400

    urgent = bool(data.get('urgent', False))
    statut = 'en_attente' if urgent or u['role'] == 'patient' else data.get('statut', 'programmé')

    # ── Conflict detection (same patient + date + heure already booked) ────────
    if rdv_date and rdv_heure:
        conflict = db.execute(
            "SELECT id FROM rdv WHERE patient_id=? AND date=? AND heure=? "
            "AND statut NOT IN ('annulé','refusé') AND (deleted IS NULL OR deleted=0)",
            (pid, rdv_date, rdv_heure)
        ).fetchone()
        if conflict:
            return jsonify({"error": f"Un rendez-vous existe déjà pour ce patient le {rdv_date} à {rdv_heure}."}), 409

    rdv_id         = "RDV" + str(uuid.uuid4())[:6].upper()
    rdv_type       = data.get('type', 'Consultation')
    rdv_medecin    = data.get('medecin', u['nom'])
    rdv_medecin_id = data.get('medecin_id', '') or (u['id'] if u['role'] == 'medecin' else '')

    try:
        db.execute(
            "INSERT INTO rdv (id,patient_id,date,heure,type,statut,medecin,medecin_id,notes,urgent,demande_par) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rdv_id, pid, rdv_date, rdv_heure,
             rdv_type, statut,
             rdv_medecin, rdv_medecin_id, data.get('notes',''),
             1 if urgent else 0, u['role'])
        )

        # ── Auto-link patient to the booking doctor if not already in their list ──
        is_new_patient_for_doctor = False
        if rdv_medecin_id:
            already_primary = (p.get('medecin_id') == rdv_medecin_id)
            already_linked  = db.execute(
                "SELECT 1 FROM patient_doctors WHERE patient_id=? AND medecin_id=?",
                (pid, rdv_medecin_id)
            ).fetchone()
            if not already_primary and not already_linked:
                db.execute(
                    "INSERT OR IGNORE INTO patient_doctors (patient_id, medecin_id) VALUES (?,?)",
                    (pid, rdv_medecin_id)
                )
                is_new_patient_for_doctor = True

        if urgent or u['role'] == 'patient':
            if is_new_patient_for_doctor:
                msg = (f"{'🚨 RDV URGENT' if urgent else '👤 Nouveau patient'} : "
                       f"{p['prenom']} {p['nom']} a demandé un RDV et a été ajouté à votre liste de patients.")
            else:
                dr_suffix = f" (Dr. {rdv_medecin})" if rdv_medecin else ""
                msg = f"{'🚨 RDV URGENT' if urgent else 'Nouveau RDV'} demandé par {p['prenom']} {p['nom']}{dr_suffix}"
            add_notif(db, "rdv_urgent" if urgent else "rdv_demande", msg, u['role'], pid,
                      {"rdv_id": rdv_id, "medecin_id": rdv_medecin_id},
                      medecin_id=rdv_medecin_id or None, commit=False)

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"add_rdv failed: {exc}")
        return jsonify({"error": "Erreur lors de la création du rendez-vous."}), 500

    # ── Send confirmation email (fire-and-forget, outside transaction) ────────
    if u['role'] == 'medecin' and statut == 'confirmé':
        _send_rdv_confirmation(p, rdv_date, rdv_heure, rdv_type, rdv_medecin)

    return jsonify({
        "ok": True,
        "rdv": {
            "id": rdv_id, "date": rdv_date, "heure": rdv_heure,
            "type": rdv_type, "statut": statut,
            "medecin": rdv_medecin, "urgent": urgent
        }
    })


def _send_rdv_confirmation(p, date_str, heure, type_rdv, medecin):
    """Fire-and-forget confirmation email after a confirmed RDV is created."""
    import threading

    def _send():
        if not p.get('email') or '@' not in p['email']:
            return
        try:
            from email_notif import send_email
            body = f"""<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px"><div style="font-size:22px;font-weight:bold;color:#fff">👁 OphtalmoScan</div></div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Confirmation de rendez-vous</h2>
    <p>Bonjour <strong>{p['prenom']} {p['nom']}</strong>,</p>
    <p>Votre rendez-vous a été confirmé :</p>
    <table style="width:100%;background:#f0faf9;border-radius:8px;border:1px solid #b2dfdb;border-collapse:collapse;margin:18px 0">
      <tr><td style="padding:10px 14px;color:#555;border-bottom:1px solid #b2dfdb">📅 Date</td><td style="padding:10px 14px;font-weight:700;border-bottom:1px solid #b2dfdb">{date_str}</td></tr>
      <tr><td style="padding:10px 14px;color:#555;border-bottom:1px solid #b2dfdb">⏰ Heure</td><td style="padding:10px 14px;font-weight:700;border-bottom:1px solid #b2dfdb">{heure}</td></tr>
      <tr><td style="padding:10px 14px;color:#555;border-bottom:1px solid #b2dfdb">🔬 Type</td><td style="padding:10px 14px;border-bottom:1px solid #b2dfdb">{type_rdv}</td></tr>
      <tr><td style="padding:10px 14px;color:#555">👨‍⚕️ Médecin</td><td style="padding:10px 14px">{medecin}</td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px">En cas d'empêchement, merci de nous contacter dès que possible.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div></body></html>"""
            send_email(p['email'], f"Confirmation RDV — {date_str} à {heure}", body)
        except Exception as e:
            logger.warning(f"RDV confirmation email failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


@bp.route('/api/rdv/<rdv_id>', methods=['DELETE'])
def delete_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute(
        "SELECT * FROM rdv WHERE id=? AND (deleted IS NULL OR deleted=0)", (rdv_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "RDV non trouvé"}), 404
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        db.execute("UPDATE suivi_postop SET statut='annulé' WHERE rdv_id=?", (rdv_id,))
        db.execute("UPDATE rdv SET deleted=1, deleted_at=? WHERE id=?", (now, rdv_id))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"delete_rdv failed: {exc}")
        return jsonify({"error": "Erreur lors de la suppression."}), 500
    return jsonify({"ok": True})


@bp.route('/api/rdv/<rdv_id>', methods=['PUT'])
def update_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM rdv WHERE id=?", (rdv_id,)).fetchone()
    if not row:
        return jsonify({"error": "RDV non trouvé"}), 404

    new_date  = data.get('date',  row['date'])
    new_heure = data.get('heure', row['heure'])

    # Conflict check when date or time changes
    if (new_date != row['date'] or new_heure != row['heure']) and new_date and new_heure:
        conflict = db.execute(
            "SELECT id FROM rdv WHERE patient_id=? AND date=? AND heure=? "
            "AND statut NOT IN ('annulé','refusé') AND id != ? "
            "AND (deleted IS NULL OR deleted=0)",
            (row['patient_id'], new_date, new_heure, rdv_id)
        ).fetchone()
        if conflict:
            return jsonify({"error": f"Un rendez-vous existe déjà pour ce patient le {new_date} à {new_heure}."}), 409

    if new_date and not valid_date(new_date):
        return jsonify({"error": "Format de date invalide (YYYY-MM-DD attendu)."}), 400
    if new_heure and not valid_heure(new_heure):
        return jsonify({"error": "Format d'heure invalide (HH:MM attendu)."}), 400

    try:
        db.execute(
            "UPDATE rdv SET date=?, heure=?, type=?, statut=?, medecin=?, notes=? WHERE id=?",
            (
                new_date,
                new_heure,
                data.get('type',   row['type']),
                data.get('statut', row['statut']),
                data.get('medecin',row['medecin']),
                data.get('notes',  row['notes']),
                rdv_id
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"update_rdv failed: {exc}")
        return jsonify({"error": "Erreur lors de la mise à jour."}), 500
    return jsonify({"ok": True})


@bp.route('/api/rdv/<rdv_id>/valider', methods=['POST'])
def valider_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    row = db.execute(
        "SELECT r.*, p.nom, p.prenom FROM rdv r JOIN patients p ON r.patient_id=p.id WHERE r.id=?",
        (rdv_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "RDV non trouvé"}), 404

    new_statut = data.get('statut', 'confirmé')
    new_notes  = data.get('notes', row['notes'])
    new_date   = data.get('date',  row['date'])
    new_heure  = data.get('heure', row['heure'])

    patient_nom    = decrypt_field(row['nom']    or '')
    patient_prenom = decrypt_field(row['prenom'] or '')

    try:
        db.execute(
            "UPDATE rdv SET statut=?, notes=?, date=?, heure=? WHERE id=?",
            (new_statut, new_notes, new_date, new_heure, rdv_id)
        )
        add_notif(db, "rdv_validé",
                  f"RDV confirmé pour {patient_prenom} {patient_nom} le {new_date}",
                  u['role'], row['patient_id'], commit=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"valider_rdv failed: {exc}")
        return jsonify({"error": "Erreur lors de la validation."}), 500

    # Send confirmation email (fire-and-forget, outside transaction)
    if new_statut == 'confirmé':
        p = db.execute("SELECT * FROM patients WHERE id=?", (row['patient_id'],)).fetchone()
        if p:
            _send_rdv_confirmation(decrypt_patient(dict(p)), new_date, new_heure, row['type'], row['medecin'])

    return jsonify({"ok": True})
