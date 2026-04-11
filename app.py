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
load_dotenv()


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


def create_app():
    _configure_logging()
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
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
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
    # All routes are JSON API endpoints in a SPA. Cross-origin CSRF is already
    # blocked by SameSite=Lax session cookies; form-based CSRF tokens are not
    # needed and cause session-cookie timing issues over plain HTTP.
    # csrf.init_app(app) is intentionally not called.

    # ── Upload folder ─────────────────────────────────────────────────────────
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads'), exist_ok=True)

    # ── Database ──────────────────────────────────────────────────────────────
    from database import init_db, close_db
    init_db(app)
    app.teardown_appcontext(close_db)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from routes.auth          import bp as auth_bp
    from routes.patients      import bp as patients_bp
    from routes.rdv           import bp as rdv_bp
    from routes.documents     import bp as docs_bp
    from routes.questions     import bp as questions_bp
    from routes.ai            import bp as ai_bp
    from routes.notifications import bp as notifs_bp
    from routes.ordonnances   import bp as ordonnances_bp
    from routes.main          import bp as main_bp
    from routes.ivt           import bp as ivt_bp
    from routes.admin         import bp as admin_bp
    from routes.agenda        import bp as agenda_bp

    for blueprint in (auth_bp, patients_bp, rdv_bp, docs_bp, questions_bp,
                      ai_bp, notifs_bp, ordonnances_bp, main_bp, ivt_bp,
                      admin_bp, agenda_bp):
        app.register_blueprint(blueprint)

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
            scheduler = BackgroundScheduler()
            scheduler.add_job(
                func=lambda: __import__('email_notif').send_rdv_email_reminders(app),
                trigger='cron', hour=8, minute=5,
                id='email_reminders', replace_existing=True
            )
            scheduler.add_job(
                func=lambda: check_postop_gaps(app),
                trigger='cron', hour=7, minute=30,
                id='postop_gaps', replace_existing=True
            )
            scheduler.start()
            import atexit
            atexit.register(lambda: scheduler.shutdown())
        except ImportError:
            pass

    return app


app = create_app()


if __name__ == '__main__':
    from llm import GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print("\n" + "=" * 60)
    print("  OphtalmoScan v2 -- SQLite Edition")
    print("=" * 60)
    if not GROQ_API_KEY:
        print("  [!] GROQ_API_KEY manquante !")
    if not GEMINI_API_KEY:
        print("  [!] GEMINI_API_KEY manquante !")
    if debug:
        print("  [!] Mode DEBUG actif — ne pas utiliser en production !")
        print("  Comptes de demonstration disponibles (voir database.py)")
        print("  AVERTISSEMENT: changez les mots de passe par defaut avant la mise en production!")
    print(f"  LLM : {GROQ_MODEL} + {GEMINI_MODEL} (fallback)")
    print(f"  DB  : ophtalmo.db (SQLite)")
    print("=" * 60 + "\n")
    app.run(debug=debug, port=5000)
