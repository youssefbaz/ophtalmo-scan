import json, uuid, datetime, logging

logger = logging.getLogger(__name__)


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

def add_notif(db, type_, message, from_role, patient_id=None, data=None, medecin_id=None, commit=True):
    db.execute(
        "INSERT INTO notifications (id,type,message,from_role,patient_id,date,lu,data,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4())[:8],
            type_, message, from_role, patient_id,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            0, json.dumps(data or {}), medecin_id or '',
        )
    )
    if commit:
        db.commit()


