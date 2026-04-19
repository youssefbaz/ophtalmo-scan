#!/usr/bin/env python3
"""
OphtalmoScan v2 — Multi-Role Ophthalmology Management Platform
Roles  : Médecin | Assistant | Patient
LLM    : Groq (llama-3.3-70b-versatile) primary + Gemini (gemini-1.5-flash) fallback
DB     : SQLite (dev) or PostgreSQL via DATABASE_URL (prod)
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
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.handlers.RotatingFileHandler(
        'ophtalmo.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _init_encryption():
    """Force .env to be loaded before security_utils initialises its Fernet
    singleton, run a round-trip self-test, and log the key fingerprint."""
    load_dotenv(_DOTENV_PATH, override=True)
    import security_utils as _su
    _su._FERNET = None
    _su._get_fernet()
    log = logging.getLogger(__name__)
    log.info("Encryption key fingerprint: %s", _su.get_key_fingerprint())
    try:
        _su.verify_encryption_key()
        log.info("Encryption key self-test: OK")
    except RuntimeError as e:
        raise RuntimeError(f"FATAL: {e} — cannot start with a broken encryption key.") from e


def _init_session_config(app: Flask) -> None:
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.secret_key = secret_key

    idle_minutes = int(os.environ.get('SESSION_IDLE_TIMEOUT', '60'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=max(idle_minutes, 30))
    app.config['SESSION_IDLE_TIMEOUT']       = idle_minutes
    app.config['SESSION_COOKIE_HTTPONLY']    = True
    app.config['SESSION_COOKIE_SAMESITE']    = 'Lax'

    # Fail-closed: SESSION_COOKIE_SECURE must be explicitly set to 0 or 1.
    secure_raw = os.environ.get('SESSION_COOKIE_SECURE')
    if secure_raw is None:
        raise RuntimeError(
            "SESSION_COOKIE_SECURE is not set. Refusing to start — this must be "
            "explicit. Set SESSION_COOKIE_SECURE=1 in production (requires HTTPS), "
            "or SESSION_COOKIE_SECURE=0 for local development."
        )
    if secure_raw not in ('0', '1'):
        raise RuntimeError(f"SESSION_COOKIE_SECURE must be '0' or '1', got {secure_raw!r}.")
    secure_cookies = (secure_raw == '1')
    app.config['SESSION_COOKIE_SECURE'] = secure_cookies
    if not secure_cookies:
        logging.getLogger(__name__).warning(
            "SESSION_COOKIE_SECURE=0 — cookies will be sent over plain HTTP. "
            "Acceptable only for local development."
        )


def _register_request_guards(app: Flask) -> None:
    """CSRF JSON-only guard + session idle timeout + activity stamp."""
    from flask import request as _req, session as _sess
    import datetime as _dt

    @app.before_request
    def _csrf_json_guard():
        if _req.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return
        if not _req.path.startswith('/api/'):
            return
        # Health and ready endpoints are probes — exempt.
        if _req.path in ('/api/health', '/api/ready'):
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
        if _sess.get('user_id'):
            _sess['_last_active'] = _dt.datetime.utcnow().isoformat()
            _sess.modified = True
        return response


def _register_blueprints(app: Flask) -> None:
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
    from routes.messages          import bp as messages_bp

    for blueprint in (auth_bp, patients_bp, patients_history_bp, patients_surgery_bp,
                      patients_account_bp, patients_import_bp,
                      rdv_bp, docs_bp, questions_bp, ai_bp, notifs_bp, ordonnances_bp,
                      main_bp, ivt_bp, admin_bp, agenda_bp, stats_bp, totp_bp, consent_bp,
                      messages_bp):
        app.register_blueprint(blueprint)


def _register_error_handlers(app: Flask) -> None:
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


def _register_admin_utilities(app: Flask) -> None:
    """Endpoints that don't fit cleanly into a blueprint but need admin auth."""
    @app.route('/api/admin/encryption-health', methods=['GET'])
    def _encryption_health():
        from database import current_user as _cu
        u = _cu()
        if not u or u['role'] != 'admin':
            return jsonify({"error": "Accès refusé"}), 403
        try:
            import security_utils as _su
            result = _su.verify_encryption_key()
            return jsonify({
                "ok":          True,
                "fingerprint": result["fingerprint"],
                "message":     "Clé de chiffrement opérationnelle — round-trip test réussi.",
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/api/email/send-reminders', methods=['POST'])
    def _trigger_email():
        from database import current_user as _cu
        u = _cu()
        if not u or u['role'] != 'medecin':
            return jsonify({"error": "Accès refusé"}), 403
        from email_notif import send_rdv_email_reminders
        sent = send_rdv_email_reminders(app)
        return jsonify({"ok": True, "sent": sent, "message": f"{sent} rappel(s) email envoyé(s)"})


def create_app():
    _configure_logging()

    from bootstrap.sentry import init_sentry
    init_sentry()

    _init_encryption()

    app = Flask(__name__)
    _init_session_config(app)

    # Rate limiter
    from extensions import limiter
    limiter.init_app(app)

    # API versioning alias — MUST register before request guards so the
    # rewrite happens before the CSRF check evaluates request.path.
    from bootstrap.versioning import install_api_v1_alias
    install_api_v1_alias(app)

    _register_request_guards(app)

    # Upload folders
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads', 'documents'), exist_ok=True)

    # Database
    from database import init_db, close_db
    init_db(app)
    app.teardown_appcontext(close_db)

    # Recover any async work stuck by a previous crash
    from bootstrap.recovery import recover_pending_analyses
    recover_pending_analyses(app)

    _register_blueprints(app)

    # Health probes — registered AFTER blueprints so they don't collide
    from bootstrap.health import register as register_health
    register_health(app)

    # Security headers
    from bootstrap.talisman import init_talisman
    init_talisman(app)

    _register_error_handlers(app)
    _register_admin_utilities(app)

    # Scheduler — last, so all routes are registered before jobs can fire
    from bootstrap.scheduler import start_scheduler
    start_scheduler(app)

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
