"""
Daily agenda view + post-op gap alert scheduler helper.
"""
import datetime
import logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, require_role, add_notif

bp = Blueprint('agenda', __name__)
logger = logging.getLogger(__name__)


# ─── DAILY AGENDA ─────────────────────────────────────────────────────────────

@bp.route('/api/agenda/day', methods=['GET'])
@require_role('medecin')
def get_day_agenda():
    """Return all RDVs for a given date (default: today) for the logged-in doctor."""
    u = current_user()
    date_str = request.args.get('date', datetime.date.today().isoformat())
    db = get_db()
    rows = db.execute("""
        SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom,
               p.telephone, p.email
        FROM rdv r
        JOIN patients p ON r.patient_id = p.id
        WHERE r.date = ? AND p.medecin_id = ?
        ORDER BY r.heure, r.id
    """, (date_str, u['id'])).fetchall()

    result = [dict(r) for r in rows]
    for r in result:
        r['urgent'] = bool(r['urgent'])
    return jsonify(result)


# ─── WEEK VIEW ────────────────────────────────────────────────────────────────

@bp.route('/api/agenda/week', methods=['GET'])
@require_role('medecin')
def get_week_agenda():
    """Return RDVs for the 7 days starting from 'date' (default: today)."""
    u = current_user()
    start = request.args.get('date', datetime.date.today().isoformat())
    try:
        start_dt = datetime.date.fromisoformat(start)
    except ValueError:
        start_dt = datetime.date.today()
    end_dt = (start_dt + datetime.timedelta(days=6)).isoformat()
    start   = start_dt.isoformat()

    db = get_db()
    rows = db.execute("""
        SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom
        FROM rdv r
        JOIN patients p ON r.patient_id = p.id
        WHERE r.date BETWEEN ? AND ? AND p.medecin_id = ?
        ORDER BY r.date, r.heure
    """, (start, end_dt, u['id'])).fetchall()

    result = [dict(r) for r in rows]
    for r in result:
        r['urgent'] = bool(r['urgent'])
    return jsonify(result)


# ─── POST-OP GAP NOTIFICATIONS (called by scheduler) ─────────────────────────

def check_postop_gaps(app):
    """Scan all patients for overdue post-op steps and create notifications.
    Meant to be called once daily by APScheduler."""
    with app.app_context():
        db = get_db()
        today = datetime.date.today().isoformat()
        rows = db.execute("""
            SELECT s.id, s.patient_id, s.etape, s.date_prevue,
                   p.nom, p.prenom, p.medecin_id
            FROM suivi_postop s
            JOIN patients p ON s.patient_id = p.id
            WHERE s.statut = 'a_faire' AND s.date_prevue < ?
        """, (today,)).fetchall()

        for row in rows:
            days_late = (datetime.date.today() -
                         datetime.date.fromisoformat(row['date_prevue'])).days
            # Only notify once every ~7 days to avoid flooding
            if days_late in (1, 7, 14, 30):
                add_notif(
                    db,
                    "postop_gap",
                    f"⚠️ Suivi post-op {row['etape']} en retard de {days_late}j "
                    f"— {row['prenom']} {row['nom']}",
                    "system",
                    row['patient_id']
                )
        logger.info(f"Post-op gap check: {len(rows)} overdue steps found for {today}.")
