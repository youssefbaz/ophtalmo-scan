"""SMS reminder module — sends Twilio SMS 1 day before RDV.

Number normalization supports:
  - Moroccan mobile  : 06XXXXXXXX / 07XXXXXXXX  →  +212 6XX XXX XXX
  - Moroccan landline: 05XXXXXXXX               →  +212 5XX XXX XXX
  - Already E.164    : +XXXXXXXXXXX             →  kept as-is
  - International    : 00XXXXXXXXXXX            →  +XXXXXXXXXXX
"""
import os, datetime, re
import logging

logger = logging.getLogger(__name__)

TWILIO_SID     = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM    = os.environ.get("TWILIO_FROM_NUMBER", "")
DEFAULT_CC     = os.environ.get("DEFAULT_COUNTRY_CODE", "212")  # Morocco


def _twilio_available():
    return bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)


def normalize_phone(raw: str) -> str:
    """Convert any common Moroccan / international format to E.164."""
    # Strip spaces, dashes, dots, parentheses
    phone = re.sub(r"[\s\-\.\(\)\/]", "", raw.strip())

    if phone.startswith("+"):
        # Already E.164
        return phone

    if phone.startswith("00"):
        # International prefix without '+' — e.g. 00212XXXXXXXXX
        return "+" + phone[2:]

    if phone.startswith("0"):
        # Local format — prepend default country code (Morocco: 212)
        # e.g.  0612345678  →  +212612345678
        return "+" + DEFAULT_CC + phone[1:]

    # Bare digits with no prefix — assume default country
    return "+" + DEFAULT_CC + phone


def send_sms(to_number: str, message: str) -> bool:
    """Send an SMS via Twilio. Returns True on success."""
    if not _twilio_available():
        logger.warning("Twilio credentials manquantes — SMS non envoyé.")
        return False
    if not to_number or not to_number.strip():
        logger.warning("Numéro de téléphone vide — SMS ignoré.")
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        phone = normalize_phone(to_number)
        client.messages.create(body=message, from_=TWILIO_FROM, to=phone)
        logger.info(f"SMS envoyé à {phone}")
        return True
    except Exception as e:
        logger.error(f"Erreur SMS Twilio: {e}")
        return False


def send_rdv_reminders(app):
    """Called by APScheduler every day at 08:00 — sends reminders for tomorrow's RDVs."""
    with app.app_context():
        from database import get_db
        db = get_db()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        rows = db.execute(
            """SELECT r.id, r.heure, r.type, r.medecin,
                      p.nom, p.prenom, p.telephone
               FROM rdv r
               JOIN patients p ON r.patient_id = p.id
               WHERE r.date=? AND r.statut IN ('confirmé','programmé') AND r.sms_envoye=0
                 AND p.telephone != ''""",
            (tomorrow,)
        ).fetchall()

        sent = 0
        for row in rows:
            msg = (
                f"Rappel RDV Ophtalmo : {row['prenom']} {row['nom']}, "
                f"demain {tomorrow} à {row['heure']} "
                f"({row['type']}) avec {row['medecin']}. "
                f"En cas d'empêchement merci de nous contacter."
            )
            if send_sms(row['telephone'], msg):
                db.execute("UPDATE rdv SET sms_envoye=1 WHERE id=?", (row['id'],))
                sent += 1

        if sent:
            db.commit()
        logger.info(f"Rappels SMS : {sent} envoyé(s) pour le {tomorrow}.")
