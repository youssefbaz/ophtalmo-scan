#!/usr/bin/env python3
"""
OphtalmoScan v2 — Multi-Role Ophthalmology Management Platform
Roles  : Médecin | Assistant | Patient
LLM    : Groq (llama-3.3-70b-versatile) primary + Gemini (gemini-1.5-flash) fallback
DB     : SQLite  → ophtalmo.db
"""
import os
import logging
import logging.handlers
from datetime import timedelta
from flask import Flask, jsonify
from dotenv import load_dotenv
# Load .env with an absolute path so it is found regardless of cwd,
# and with override=True so env vars set after a first (bad) load are corrected.
_DOTENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_DOTENV_PATH, override=True)


def _configure_logging():
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # stdout
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    # rotating file — 5 MB × 3 backups
    fh = logging.handlers.RotatingFileHandler(
        'ophtalmo.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _init_sentry():
    """Initialise Sentry error monitoring if SENTRY_DSN is configured."""
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.05,   # 5% of transactions for performance monitoring
            send_default_pii=False,    # never send PII to Sentry
        )
        logging.getLogger(__name__).info("Sentry error monitoring initialised")
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Run: pip install sentry-sdk[flask]"
        )


def create_app():
    _configure_logging()
    _init_sentry()

    # Force .env to be loaded (with correct absolute path) before any security
    # module initialises its Fernet singleton. Also reset the singleton so that
    # if security_utils was imported before this point it gets re-keyed.
    load_dotenv(_DOTENV_PATH, override=True)
    import security_utils as _su
    _su._FERNET = None  # discard any singleton built before the key was available
    # Trigger key initialisation now so the backup/warning fires at startup,
    # then log the fingerprint so operators can verify key consistency.
    _su._get_fernet()
    logging.getLogger(__name__).info(
        "Encryption key fingerprint: %s", _su.get_key_fingerprint()
    )
    # Self-test: verify the key can round-trip encrypt/decrypt before serving traffic
    try:
        _su.verify_encryption_key()
        logging.getLogger(__name__).info("Encryption key self-test: OK")
    except RuntimeError as _e:
        raise RuntimeError(f"FATAL: {_e} — cannot start with a broken encryption key.") from _e

    app = Flask(__name__)

    # ── Secret key (hard-fail if missing) ────────────────────────────────────
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.secret_key = secret_key

    # ── Session config ────────────────────────────────────────────────────────
    # Idle timeout: clear session after N minutes of inactivity (default 30).
    # Absolute lifetime is set higher so a legitimately active session is never
    # cut short by the cookie expiry before the idle check fires.
    idle_minutes = int(os.environ.get('SESSION_IDLE_TIMEOUT', '30'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=max(idle_minutes, 30))
    app.config['SESSION_IDLE_TIMEOUT']       = idle_minutes
    app.config['SESSION_COOKIE_HTTPONLY']    = True
    app.config['SESSION_COOKIE_SAMESITE']    = 'Lax'
    # Set SESSION_COOKIE_SECURE=1 in production (HTTPS only).
    # Defaults to False so cookies are sent over plain HTTP in development.
    secure_cookies = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    app.config['SESSION_COOKIE_SECURE'] = secure_cookies
    if not secure_cookies and not app.debug:
        logging.getLogger(__name__).warning(
            "SESSION_COOKIE_SECURE is not set — cookies will be sent over plain HTTP. "
            "Set SESSION_COOKIE_SECURE=1 in production (requires HTTPS)."
        )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    from extensions import csrf, limiter
    limiter.init_app(app)

    # ── CSRF ──────────────────────────────────────────────────────────────────
    # This is a JSON-only SPA. We enforce two complementary defences:
    #   1. SameSite=Lax cookies — browsers won't attach the session cookie on
    #      cross-origin navigations (covers the vast majority of CSRF vectors).
    #   2. Content-Type check (below) — browsers cannot send cross-origin
    #      application/json without a CORS preflight, which we never approve.
    # Together these are equivalent to a synchronizer-token in practice.
    # Full csrf.init_app(app) is deliberately omitted — it requires HTTPS and
    # template integration that would break the SPA flow.
    from flask import request as _req, session as _sess
    import datetime as _dt

    @app.before_request
    def _csrf_json_guard():
        """Reject mutating non-JSON requests to /api/* — effective CSRF barrier."""
        if _req.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return
        if not _req.path.startswith('/api/'):
            return
        ct  = _req.content_type or ''
        xrw = _req.headers.get('X-Requested-With', '')
        if 'application/json' not in ct and xrw != 'XMLHttpRequest':
            logging.getLogger(__name__).warning(
                "CSRF guard blocked %s %s (Content-Type=%r, X-Requested-With=%r)",
                _req.method, _req.path, ct, xrw
            )
            return jsonify({"error": "Requête invalide"}), 400

    @app.before_request
    def _check_session_idle():
        """Expire session after SESSION_IDLE_TIMEOUT minutes of inactivity."""
        last = _sess.get('_last_active')
        if not last:
            return
        idle = app.config.get('SESSION_IDLE_TIMEOUT', 30)
        try:
            delta = (_dt.datetime.utcnow() -
                     _dt.datetime.fromisoformat(last)).total_seconds()
            if delta > idle * 60:
                _sess.clear()
        except Exception:
            _sess.clear()

    @app.after_request
    def _refresh_session_activity(response):
        """Stamp last-active on every authenticated response."""
        if _sess.get('user_id'):
            _sess['_last_active'] = _dt.datetime.utcnow().isoformat()
            _sess.modified = True
        return response

    # ── Upload folder ─────────────────────────────────────────────────────────
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads', 'documents'), exist_ok=True)

    # ── Database ──────────────────────────────────────────────────────────────
    from database import init_db, close_db
    init_db(app)
    app.teardown_appcontext(close_db)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from routes.auth              import bp as auth_bp
    from routes.patients          import bp as patients_bp
    from routes.patients_history  import bp as patients_history_bp
    from routes.patients_surgery  import bp as patients_surgery_bp
    from routes.patients_account  import bp as patients_account_bp
    from routes.patients_import   import bp as patients_import_bp
    from routes.rdv               import bp as rdv_bp
    from routes.documents         import bp as docs_bp
    from routes.questions         import bp as questions_bp
    from routes.ai                import bp as ai_bp
    from routes.notifications     import bp as notifs_bp
    from routes.ordonnances       import bp as ordonnances_bp
    from routes.main              import bp as main_bp
    from routes.ivt               import bp as ivt_bp
    from routes.admin             import bp as admin_bp
    from routes.agenda            import bp as agenda_bp
    from routes.stats             import bp as stats_bp
    from routes.totp              import bp as totp_bp
    from routes.consent           import bp as consent_bp

    for blueprint in (auth_bp, patients_bp, patients_history_bp, patients_surgery_bp,
                      patients_account_bp, patients_import_bp,
                      rdv_bp, docs_bp, questions_bp, ai_bp, notifs_bp, ordonnances_bp,
                      main_bp, ivt_bp, admin_bp, agenda_bp, stats_bp, totp_bp, consent_bp):
        app.register_blueprint(blueprint)

    # ── Flask-Talisman (Step 7 — Security headers / HTTPS) ───────────────────
    # Only enforce HTTPS in production (SESSION_COOKIE_SECURE=1).
    # In development (plain HTTP) Talisman is initialised but HTTPS is not forced.
    try:
        from flask_talisman import Talisman
        _force_https = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
        Talisman(
            app,
            force_https=_force_https,
            strict_transport_security=_force_https,
            strict_transport_security_max_age=31536000,
            content_security_policy={
                'default-src': ["'self'"],
                'script-src':  ["'self'", "'unsafe-inline'",
                                 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com'],
                'style-src':   ["'self'", "'unsafe-inline'",
                                 'cdn.jsdelivr.net', 'fonts.googleapis.com'],
                'font-src':    ["'self'", 'fonts.gstatic.com', 'data:'],
                'img-src':     ["'self'", 'data:', 'blob:'],
                'connect-src': ["'self'"],
                'frame-ancestors': ["'none'"],
            },
            referrer_policy='strict-origin-when-cross-origin',
            feature_policy={
                'geolocation': "'none'",
                'camera':      "'none'",
                'microphone':  "'none'",
            },
            session_cookie_secure=_force_https,
        )
        logging.getLogger(__name__).info(
            f"Talisman initialised (force_https={_force_https})"
        )
    except ImportError:
        logging.getLogger(__name__).warning(
            "flask-talisman not installed — security headers not applied. "
            "Run: pip install flask-talisman"
        )

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Requête invalide", "detail": str(e)}), 400

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Accès refusé"}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Ressource non trouvée"}), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Trop de tentatives. Réessayez dans une minute."}), 429

    @app.errorhandler(500)
    def server_error(e):
        logging.getLogger(__name__).exception("Unhandled server error")
        return jsonify({"error": "Erreur serveur interne"}), 500

    # ── Encryption health check (admin) ──────────────────────────────────────
    @app.route('/api/admin/encryption-health', methods=['GET'])
    def encryption_health():
        from database import current_user as _cu
        u = _cu()
        if not u or u['role'] != 'admin':
            return jsonify({"error": "Accès refusé"}), 403
        try:
            import security_utils as _su2
            result = _su2.verify_encryption_key()
            return jsonify({
                "ok":          True,
                "fingerprint": result["fingerprint"],
                "message":     "Clé de chiffrement opérationnelle — round-trip test réussi.",
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Manual email reminder trigger ─────────────────────────────────────────
    @app.route('/api/email/send-reminders', methods=['POST'])
    def trigger_email():
        from database import current_user as _cu
        u = _cu()
        if not u or u['role'] != 'medecin':
            return jsonify({"error": "Accès refusé"}), 403
        from email_notif import send_rdv_email_reminders
        sent = send_rdv_email_reminders(app)
        return jsonify({"ok": True, "sent": sent, "message": f"{sent} rappel(s) email envoyé(s)"})

    # ── APScheduler: daily reminders at 08:00 ────────────────────────────────
    # Only start scheduler in the main process (not Werkzeug reloader child)
    if not os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or \
            os.environ.get('FLASK_DEBUG', '0') != '1':
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from routes.agenda import check_postop_gaps
            _sched_log = logging.getLogger('apscheduler.startup')
            scheduler = BackgroundScheduler()
            scheduler.add_job(
                func=lambda: __import__('email_notif').send_rdv_email_reminders(app),
                trigger='cron', hour=8, minute=5,
                id='email_reminders', replace_existing=True
            )
            _sched_log.info("Scheduled job registered: email_reminders (daily 08:05)")
            scheduler.add_job(
                func=lambda: check_postop_gaps(app),
                trigger='cron', hour=7, minute=30,
                id='postop_gaps', replace_existing=True
            )
            _sched_log.info("Scheduled job registered: postop_gaps (daily 07:30)")
            # Daily encrypted database backup at 02:00
            def _run_backup():
                try:
                    import backup as _bk
                    path = _bk.run_backup()
                    _sched_log.info(f"Scheduled backup completed: {path}")
                except Exception as _e:
                    _sched_log.error(f"Scheduled backup failed: {_e}")
            scheduler.add_job(
                func=_run_backup,
                trigger='cron', hour=2, minute=0,
                id='daily_backup', replace_existing=True
            )
            _sched_log.info("Scheduled job registered: daily_backup (daily 02:00)")
            scheduler.start()
            _sched_log.info(
                "APScheduler started — %d job(s) registered: %s",
                len(scheduler.get_jobs()),
                [j.id for j in scheduler.get_jobs()]
            )
            import atexit
            atexit.register(lambda: scheduler.shutdown())
        except ImportError:
            pass

    return app


app = create_app()


if __name__ == '__main__':
    from llm import GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL
    from security_utils import get_key_fingerprint
    _log = logging.getLogger(__name__)
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    _log.info("OphtalmoScan v2 — SQLite Edition — starting up")
    _log.info("LLM: %s + %s (fallback)", GROQ_MODEL, GEMINI_MODEL)
    _log.info("Encryption key fingerprint: %s", get_key_fingerprint())
    if not GROQ_API_KEY:
        _log.warning("GROQ_API_KEY is not set — primary LLM unavailable")
    if not GEMINI_API_KEY:
        _log.warning("GEMINI_API_KEY is not set — Gemini fallback unavailable")
    if debug:
        _log.warning("FLASK_DEBUG is active — do NOT use in production")
        _log.warning("Demo accounts active — change default passwords before going live")
    app.run(debug=debug, port=5000)
