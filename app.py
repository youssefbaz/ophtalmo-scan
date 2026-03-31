#!/usr/bin/env python3
"""
OphtalmoScan v2 — Multi-Role Ophthalmology Management Platform
Roles  : Médecin | Assistant | Patient
LLM    : Groq (llama-3.3-70b-versatile) primary + Gemini (gemini-1.5-flash) fallback
DB     : SQLite  → ophtalmo.db
"""
import os
from flask import Flask
from dotenv import load_dotenv
load_dotenv()


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "ophthalmo_v2_secret_2025")

    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads'), exist_ok=True)

    # Database init + teardown
    from database import init_db, close_db
    init_db(app)
    app.teardown_appcontext(close_db)

    # Blueprints
    from routes.auth          import bp as auth_bp
    from routes.patients      import bp as patients_bp
    from routes.rdv           import bp as rdv_bp
    from routes.documents     import bp as docs_bp
    from routes.questions     import bp as questions_bp
    from routes.ai            import bp as ai_bp
    from routes.notifications import bp as notifs_bp
    from routes.ordonnances   import bp as ordonnances_bp
    from routes.main          import bp as main_bp

    for blueprint in (auth_bp, patients_bp, rdv_bp, docs_bp, questions_bp,
                      ai_bp, notifs_bp, ordonnances_bp, main_bp):
        app.register_blueprint(blueprint)

    return app


app = create_app()


if __name__ == '__main__':
    from llm import GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL
    print("\n" + "=" * 60)
    print("  OphtalmoScan v2 -- SQLite Edition")
    print("=" * 60)
    if not GROQ_API_KEY:
        print("  [!] GROQ_API_KEY manquante !")
    if not GEMINI_API_KEY:
        print("  [!] GEMINI_API_KEY manquante !")
    if not os.environ.get("SECRET_KEY"):
        print("  [!] SECRET_KEY non definie, utilisation du fallback de dev.")
    print("  Comptes de demonstration :")
    print("  Medecin   : dr.martin / medecin123")
    print("  Patient 1 : patient.marie / patient123")
    print("  Patient 2 : patient.jp / patient123")
    print("=" * 60)
    print(f"  LLM : {GROQ_MODEL} + {GEMINI_MODEL} (fallback)")
    print(f"  DB  : ophtalmo.db (SQLite)")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
