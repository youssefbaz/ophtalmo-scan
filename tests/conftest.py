"""Shared pytest fixtures — session-scoped app + seeded DB.

Defining these here (not in test_smoke.py) means every test module picks up
the same session-scoped instance. Previously fixtures were local to
test_smoke.py, so importing them from a second test file double-initialised
the app and broke table creation ordering.
"""
import os
import sys
import tempfile
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="session")
def app_and_db():
    from dotenv import load_dotenv as _ldenv
    _ldenv(override=False)

    os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
    os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
    os.environ["RATELIMIT_ENABLED"] = "0"
    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        os.environ["FIELD_ENCRYPTION_KEY"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.environ["OPHTALMO_DB_PATH"] = db_path
    os.environ["DATABASE_URL"]     = ""

    import database as _db
    _db.DB_PATH  = db_path
    _db.DATABASE = db_path
    _db._USE_PG  = False

    from app import create_app
    application = create_app()
    application.config["TESTING"]              = True
    application.config["RATELIMIT_ENABLED"]    = False
    application.config["WTF_CSRF_ENABLED"]     = False

    with application.app_context():
        _db.init_db(application)
        _seed_test_users(db_path)

    yield application, db_path

    os.close(db_fd)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _seed_test_users(db_path):
    from werkzeug.security import generate_password_hash
    from security_utils import encrypt_patient_fields

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    for uid, username, role in [
        ("MED_A", "medecin_a", "medecin"),
        ("MED_B", "medecin_b", "medecin"),
    ]:
        cur.execute(
            "INSERT OR IGNORE INTO users "
            "(id,username,password_hash,role,nom,prenom,status,totp_enabled,locked_until) "
            "VALUES (?,?,?,?,?,?,?,0,'')",
            (uid, username, generate_password_hash("SecurePass@2025!"),
             role, "Test", "Dr", "active")
        )

    cur.execute(
        "INSERT OR IGNORE INTO users "
        "(id,username,password_hash,role,nom,prenom,status,totp_enabled,locked_until) "
        "VALUES (?,?,?,?,?,?,?,0,'')",
        ("ADMIN_T", "admin_test", generate_password_hash("AdminPass@2025!"),
         "admin", "Admin", "Test", "active")
    )

    pii = encrypt_patient_fields({
        "nom":"Dupont","prenom":"Alice","ddn":"1980-01-01","telephone":"","email":""
    })
    cur.execute(
        "INSERT OR IGNORE INTO patients "
        "(id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id,birth_year) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("P_A001", pii["nom"], pii["prenom"], pii["ddn"],
         "F", pii["telephone"], pii["email"], "[]", "[]", "MED_A", 1980)
    )

    cur.execute(
        "INSERT OR IGNORE INTO users "
        "(id,username,password_hash,role,nom,prenom,patient_id,status,totp_enabled,locked_until) "
        "VALUES (?,?,?,?,?,?,?,?,0,'')",
        ("PAT_A", "patient_a", generate_password_hash("SecurePass@2025!"),
         "patient", "Dupont", "Alice", "P_A001", "active")
    )
    con.commit()
    con.close()


@pytest.fixture
def app(app_and_db):
    application, _ = app_and_db
    return application


@pytest.fixture
def db_path(app_and_db):
    _, path = app_and_db
    return path


@pytest.fixture
def client(app):
    return app.test_client()
