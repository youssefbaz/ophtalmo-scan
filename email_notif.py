"""Email notification module — sends reminders via SMTP.

Supports any SMTP provider (Gmail, Outlook, Mailjet SMTP, etc.).
Set SMTP_HOST=smtp.gmail.com, SMTP_PORT=587 for Gmail with App Password.
"""
import os, smtplib, datetime, logging, html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM    = os.environ.get("EMAIL_FROM", "") or SMTP_USER


def _smtp_available():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to_address: str, subject: str, body_html: str) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if not _smtp_available():
        logger.warning("SMTP credentials missing — email not sent.")
        return False
    if not to_address or '@' not in to_address:
        logger.warning(f"Invalid email address '{to_address}' — ignored.")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = EMAIL_FROM
        msg['To']      = to_address
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [to_address], msg.as_string())
        logger.info(f"Email sent to {to_address}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email error ({to_address}): {e}")
        return False


def send_credentials_email(to_address: str, prenom: str, nom: str,
                           username: str, password: str, app_host: str = '') -> bool:
    """Send login credentials to a newly created patient account."""
    login_url  = f"{app_host}/" if app_host else "l'application"
    h_prenom   = html.escape(prenom)
    h_nom      = html.escape(nom)
    h_username = html.escape(username)
    h_password = html.escape(password)
    body = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff">👁 OphtalmoScan</div>
    <div style="font-size:13px;color:rgba(255,255,255,.8);margin-top:4px">Votre espace patient</div>
  </div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Bienvenue, {h_prenom} {h_nom} !</h2>
    <p>Votre dossier patient a été créé. Voici vos identifiants de connexion :</p>
    <table style="width:100%;background:#f0faf9;border-radius:8px;border:1px solid #b2dfdb;border-collapse:collapse;margin:18px 0">
      <tr>
        <td style="padding:12px 16px;color:#555;border-bottom:1px solid #b2dfdb;width:40%">🔑 Identifiant</td>
        <td style="padding:12px 16px;font-weight:700;font-family:monospace;font-size:15px;border-bottom:1px solid #b2dfdb">{h_username}</td>
      </tr>
      <tr>
        <td style="padding:12px 16px;color:#555">🔒 Mot de passe</td>
        <td style="padding:12px 16px;font-weight:700;font-family:monospace;font-size:15px">{h_password}</td>
      </tr>
    </table>
    <p style="font-size:13px;color:#374151">Connectez-vous sur <a href="{login_url}" style="color:#0e7a76">{html.escape(login_url) or "l'application"}</a> pour consulter vos rendez-vous, documents et poser des questions à votre médecin.</p>
    <div style="background:#fff8e1;border:1px solid #f59e0b;border-radius:8px;padding:12px 16px;margin-top:18px;font-size:12px;color:#92400e">
      ⚠️ Conservez ces identifiants en lieu sûr. Nous ne vous demanderons jamais votre mot de passe par téléphone.
    </div>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div>
</body></html>"""
    return send_email(to_address, "Vos identifiants OphtalmoScan", body)


def send_account_validated_email(to_address: str, prenom: str, nom: str,
                                  username: str, app_host: str = '') -> bool:
    """Notify a médecin that their account has been validated by the admin."""
    login_url  = f"{app_host}/" if app_host else "l'application"
    h_prenom   = html.escape(prenom)
    h_nom      = html.escape(nom)
    h_username = html.escape(username)
    body = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff">👁 OphtalmoScan</div>
    <div style="font-size:13px;color:rgba(255,255,255,.8);margin-top:4px">Système de gestion ophtalmologique</div>
  </div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Votre compte a été activé</h2>
    <p>Bonjour Dr. <strong>{h_prenom} {h_nom}</strong>,</p>
    <p>Nous avons le plaisir de vous informer que votre compte OphtalmoScan a été <strong style="color:#0e7a76">validé par l'administrateur</strong>.</p>
    <p>Vous pouvez dès maintenant vous connecter avec votre identifiant :</p>
    <table style="width:100%;background:#f0faf9;border-radius:8px;border:1px solid #b2dfdb;border-collapse:collapse;margin:18px 0">
      <tr>
        <td style="padding:12px 16px;color:#555;width:40%">🔑 Identifiant</td>
        <td style="padding:12px 16px;font-weight:700;font-family:monospace;font-size:15px">{h_username}</td>
      </tr>
    </table>
    <div style="text-align:center;margin:24px 0">
      <a href="{login_url}" style="background:#0e7a76;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">
        Se connecter
      </a>
    </div>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div>
</body></html>"""
    return send_email(to_address, "Votre compte OphtalmoScan a été activé", body)


def _rdv_html(prenom, nom, date_str, heure, type_rdv, medecin):
    h_prenom   = html.escape(prenom)
    h_nom      = html.escape(nom)
    h_date     = html.escape(str(date_str))
    h_heure    = html.escape(str(heure))
    h_type_rdv = html.escape(str(type_rdv))
    h_medecin  = html.escape(str(medecin))
    return f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff;letter-spacing:1px">👁 OphtalmoScan</div>
    <div style="font-size:13px;color:rgba(255,255,255,.8);margin-top:4px">Cabinet d'Ophtalmologie</div>
  </div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Rappel de rendez-vous</h2>
    <p>Bonjour <strong>{h_prenom} {h_nom}</strong>,</p>
    <p>Nous vous rappelons votre rendez-vous de demain :</p>
    <table style="width:100%;background:#f9f9f9;border-radius:8px;border:1px solid #e5e7eb;border-collapse:collapse;margin:16px 0">
      <tr><td style="padding:10px 14px;color:#666;border-bottom:1px solid #e5e7eb">📅 Date</td><td style="padding:10px 14px;font-weight:700;border-bottom:1px solid #e5e7eb">{h_date}</td></tr>
      <tr><td style="padding:10px 14px;color:#666;border-bottom:1px solid #e5e7eb">⏰ Heure</td><td style="padding:10px 14px;font-weight:700;border-bottom:1px solid #e5e7eb">{h_heure}</td></tr>
      <tr><td style="padding:10px 14px;color:#666;border-bottom:1px solid #e5e7eb">🔬 Type</td><td style="padding:10px 14px;border-bottom:1px solid #e5e7eb">{h_type_rdv}</td></tr>
      <tr><td style="padding:10px 14px;color:#666">👨‍⚕️ Médecin</td><td style="padding:10px 14px">{h_medecin}</td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px">En cas d'empêchement, merci de nous contacter dès que possible.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div>
</body></html>"""


def send_rdv_email_reminders(app):
    """Send email reminders for tomorrow's RDVs (called by scheduler)."""
    with app.app_context():
        from database import get_db
        from security_utils import decrypt_field
        db = get_db()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        rows = db.execute(
            """SELECT r.id, r.heure, r.type, r.medecin,
                      p.nom, p.prenom, p.email
               FROM rdv r
               JOIN patients p ON r.patient_id = p.id
               WHERE r.date = ? AND r.statut IN ('confirmé','programmé')
                 AND r.email_envoye = 0
                 AND p.email != '' AND p.email IS NOT NULL""",
            (tomorrow,)
        ).fetchall()

        sent = 0
        for row in rows:
            email  = decrypt_field(row['email']  or '')
            prenom = decrypt_field(row['prenom'] or '')
            nom    = decrypt_field(row['nom']    or '')
            if not email or '@' not in email:
                continue
            subject = f"Rappel RDV Ophtalmologie — {tomorrow} à {row['heure']}"
            body    = _rdv_html(prenom, nom, tomorrow, row['heure'], row['type'], row['medecin'])
            if send_email(email, subject, body):
                db.execute("UPDATE rdv SET email_envoye=1 WHERE id=?", (row['id'],))
                sent += 1

        if sent:
            db.commit()
        logger.info(f"Email reminders: {sent}/{len(rows)} sent for {tomorrow}.")
        return sent
