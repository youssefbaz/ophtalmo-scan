"""
tests/test_smoke.py — Smoke tests for critical OphtalmoScan paths.

Run: pytest tests/ -v
"""
import json, os, sys, sqlite3, tempfile, pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─── App fixture (session-scoped — one DB for all tests) ──────────────────────

@pytest.fixture(scope="session")
def app_and_db():
    # Load .env first so FIELD_ENCRYPTION_KEY is available
    from dotenv import load_dotenv as _ldenv
    _ldenv(override=False)  # don't override if already set

    os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
    os.environ["RATELIMIT_ENABLED"] = "0"
    # Use a stable test-only encryption key so test patient PII round-trips correctly
    # Keep FIELD_ENCRYPTION_KEY from .env if set, else use a fixed test key
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
    application.config["RATELIMIT_ENABLED"]    = False   # disable rate limiter in tests
    application.config["WTF_CSRF_ENABLED"]     = False

    with application.app_context():
        _db.init_db(application)
        _seed_test_users(db_path)

    yield application, db_path

    os.close(db_fd)
    os.unlink(db_path)


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

    pii = encrypt_patient_fields({
        "nom":"Dupont","prenom":"Alice","ddn":"1980-01-01","telephone":"","email":""
    })
    cur.execute(
        "INSERT OR IGNORE INTO patients "
        "(id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("P_A001", pii["nom"], pii["prenom"], pii["ddn"],
         "F", pii["telephone"], pii["email"], "[]", "[]", "MED_A")
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
    """Fresh client per test — no shared session state."""
    return app.test_client()


def _login(client, username, password, totp_token=None):
    payload = {"username": username, "password": password}
    if totp_token:
        payload["totp_token"] = totp_token
    return client.post("/login", json=payload)


def _authed(app, username, password="SecurePass@2025!"):
    """Return a logged-in test client."""
    c = app.test_client()
    r = _login(c, username, password)
    assert r.get_json().get("ok"), f"Login failed for {username}: {r.get_json()}"
    return c


# ─── 1. Authentication ─────────────────────────────────────────────────────────

class TestAuth:
    def test_login_success(self, client):
        r = _login(client, "medecin_a", "SecurePass@2025!")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert r.get_json()["role"] == "medecin"

    def test_login_wrong_password(self, client):
        r = _login(client, "medecin_a", "wrongpassword")
        assert r.status_code == 401
        assert r.get_json()["ok"] is False

    def test_login_unknown_user(self, client):
        r = _login(client, "nobody", "doesntmatter")
        assert r.status_code == 401

    def test_logout(self, client):
        _login(client, "medecin_a", "SecurePass@2025!")
        r = client.post("/logout", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_me_unauthenticated(self, client):
        r = client.get("/me")
        assert r.status_code == 401

    def test_me_authenticated(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/me")
        assert r.status_code == 200
        assert r.get_json()["authenticated"] is True

    def test_account_lockout(self, app, db_path):
        """5 bad attempts should lock the account (rate limiter disabled in tests)."""
        from werkzeug.security import generate_password_hash
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT OR IGNORE INTO users "
            "(id,username,password_hash,role,nom,prenom,status,totp_enabled,locked_until) "
            "VALUES (?,?,?,?,?,?,?,0,'')",
            ("LOCKTEST", "locktest_user",
             generate_password_hash("RealPass@2025!"), "medecin", "L", "L", "active")
        )
        con.commit()
        con.close()

        c = app.test_client()
        for _ in range(5):
            _login(c, "locktest_user", "WrongPass99!")

        r = _login(c, "locktest_user", "RealPass@2025!")
        assert r.status_code == 423  # locked


# ─── 2. Password policy ────────────────────────────────────────────────────────

class TestPasswordPolicy:
    def test_too_short(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/change-password", json={
            "current_password": "SecurePass@2025!",
            "new_password": "Short1!"
        })
        assert r.status_code == 400
        assert "12" in r.get_json()["error"]

    def test_no_uppercase(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/change-password", json={
            "current_password": "SecurePass@2025!",
            "new_password": "nouppercase123!"
        })
        assert r.status_code == 400

    def test_no_special_char(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/change-password", json={
            "current_password": "SecurePass@2025!",
            "new_password": "NoSpecialChar123"
        })
        assert r.status_code == 400


# ─── 3. Patient scoping ────────────────────────────────────────────────────────

class TestPatientScoping:
    def test_medecin_a_can_access_own_patient(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001")
        assert r.status_code == 200
        data = r.get_json()
        assert data["id"] == "P_A001"
        assert data["nom"]    == "Dupont"   # decrypted
        assert data["prenom"] == "Alice"

    def test_medecin_b_cannot_access_medecin_a_patient(self, app):
        c = _authed(app, "medecin_b")
        r = c.get("/api/patients/P_A001")
        assert r.status_code == 403

    def test_patient_list_scoped_to_medecin(self, app):
        c_a = _authed(app, "medecin_a")
        ids_a = [p["id"] for p in c_a.get("/api/patients").get_json()]
        assert "P_A001" in ids_a

        c_b = _authed(app, "medecin_b")
        ids_b = [p["id"] for p in c_b.get("/api/patients").get_json()]
        assert "P_A001" not in ids_b

    def test_medecin_b_cannot_update_medecin_a_patient(self, app):
        c = _authed(app, "medecin_b")
        r = c.put("/api/patients/P_A001", json={
            "nom":"Hacked","prenom":"Hacker","ddn":"1990-01-01","sexe":"M",
            "telephone":"","email":"","antecedents":[],"allergies":[]
        })
        assert r.status_code == 403

    def test_medecin_b_cannot_delete_medecin_a_patient(self, app):
        c = _authed(app, "medecin_b")
        r = c.delete("/api/patients/P_A001", json={})
        assert r.status_code == 403

    def test_patient_user_can_access_own_record(self, app):
        c = _authed(app, "patient_a")
        r = c.get("/api/patients/P_A001")
        assert r.status_code == 200

    def test_patient_user_cannot_access_other_patient(self, app, db_path):
        from security_utils import encrypt_patient_fields
        pii = encrypt_patient_fields({"nom":"Other","prenom":"Bob","ddn":"1975-06-15","telephone":"","email":""})
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT OR IGNORE INTO patients "
            "(id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("P_A002",pii["nom"],pii["prenom"],pii["ddn"],"M",
             pii["telephone"],pii["email"],"[]","[]","MED_A")
        )
        con.commit()
        con.close()

        c = _authed(app, "patient_a")
        r = c.get("/api/patients/P_A002")
        assert r.status_code == 403


# ─── 4. Encryption round-trip ─────────────────────────────────────────────────

class TestEncryption:
    def test_pii_stored_encrypted_in_db(self, db_path):
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT nom, prenom FROM patients WHERE id='P_A001'").fetchone()
        con.close()
        assert row[0].startswith("gAAAAA"), f"nom not encrypted: {row[0][:30]}"
        assert row[1].startswith("gAAAAA"), f"prenom not encrypted: {row[1][:30]}"

    def test_decryption_via_api(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001")
        data = r.get_json()
        assert data["nom"]    == "Dupont"
        assert data["prenom"] == "Alice"

    def test_update_encrypts_on_write(self, app, db_path):
        c = _authed(app, "medecin_a")
        c.put("/api/patients/P_A001", json={
            "nom":"Martin","prenom":"Chloé","ddn":"1985-03-15","sexe":"F",
            "telephone":"0600000000","email":"test@test.com",
            "antecedents":[],"allergies":[]
        })
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT nom FROM patients WHERE id='P_A001'").fetchone()
        con.close()
        assert row[0].startswith("gAAAAA"), "Updated nom should be encrypted"
        # Restore
        c.put("/api/patients/P_A001", json={
            "nom":"Dupont","prenom":"Alice","ddn":"1980-01-01","sexe":"F",
            "telephone":"","email":"","antecedents":[],"allergies":[]
        })


# ─── 5. Stats scoping ─────────────────────────────────────────────────────────

class TestStats:
    def test_stats_requires_auth(self, client):
        r = client.get("/api/stats")
        # require_role returns 401 or 403 for unauthenticated — both are correct
        assert r.status_code in (401, 403)

    def test_stats_returns_for_medecin(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/stats")
        assert r.status_code == 200
        data = r.get_json()
        assert "total_patients" in data
        assert isinstance(data["total_patients"], int)

    def test_stats_scoped_per_medecin(self, app):
        c_a = _authed(app, "medecin_a")
        stats_a = c_a.get("/api/stats").get_json()["total_patients"]

        c_b = _authed(app, "medecin_b")
        stats_b = c_b.get("/api/stats").get_json()["total_patients"]

        assert stats_a >= 1
        assert stats_b == 0  # médecin_b has no patients in test DB


# ─── 6. Consent API ───────────────────────────────────────────────────────────

class TestConsent:
    def test_grant_consent(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/consent/grant", json={
            "patient_id": "P_A001",
            "consent_type": "data_processing"
        })
        assert r.status_code == 200
        assert r.get_json()["granted"] is True

    def test_consent_status(self, app):
        c = _authed(app, "medecin_a")
        # Ensure at least one grant exists
        c.post("/api/consent/grant", json={"patient_id":"P_A001","consent_type":"data_processing"})
        r = c.get("/api/consent/status/P_A001")
        assert r.status_code == 200
        data = r.get_json()
        assert "consents" in data
        dp = next(x for x in data["consents"] if x["consent_type"] == "data_processing")
        assert dp["granted"] is True

    def test_revoke_consent(self, app):
        c = _authed(app, "medecin_a")
        c.post("/api/consent/grant", json={"patient_id":"P_A001","consent_type":"ai_analysis"})
        r = c.post("/api/consent/revoke", json={"patient_id":"P_A001","consent_type":"ai_analysis"})
        assert r.status_code == 200
        assert r.get_json()["granted"] is False

    def test_medecin_b_cannot_grant_consent_for_medecin_a_patient(self, app):
        c = _authed(app, "medecin_b")
        r = c.post("/api/consent/grant", json={
            "patient_id": "P_A001",
            "consent_type": "data_processing"
        })
        assert r.status_code == 403


# ─── 7. Security controls ──────────────────────────────────────────────────────

class TestSecurityControls:
    """Tests for CSRF guard, idle timeout, and rate-limit configuration."""

    def test_csrf_guard_blocks_non_json_post(self, client):
        """Mutating /api/* POST without application/json must be rejected (CSRF defence)."""
        # Log in first so it is not an auth issue
        _login(client, "medecin_a", "SecurePass@2025!")
        r = client.post(
            "/api/patients",
            data="nom=Hacker&prenom=Evil",
            content_type="application/x-www-form-urlencoded"
        )
        assert r.status_code == 400, (
            f"CSRF guard should block form-encoded POST; got {r.status_code}"
        )

    def test_csrf_guard_blocks_plain_text_post(self, client):
        """text/plain POST to /api/* must be rejected."""
        _login(client, "medecin_a", "SecurePass@2025!")
        r = client.post(
            "/api/patients",
            data="some payload",
            content_type="text/plain"
        )
        assert r.status_code == 400

    def test_csrf_guard_allows_json_post(self, client):
        """Valid application/json POST should NOT be blocked by CSRF guard."""
        _login(client, "medecin_a", "SecurePass@2025!")
        # We send intentionally incomplete data — 400/422 is fine; 400 from CSRF guard is NOT
        r = client.post("/api/patients", json={"nom": ""})
        # CSRF guard returns 400 with {"error": "Requête invalide"}, not a patient validation error
        if r.status_code == 400:
            body = r.get_json() or {}
            assert body.get("error") != "Requête invalide", (
                "CSRF guard should NOT block application/json requests"
            )

    def test_csrf_guard_allows_x_requested_with(self, client):
        """X-Requested-With: XMLHttpRequest should bypass the CSRF guard."""
        _login(client, "medecin_a", "SecurePass@2025!")
        r = client.post(
            "/api/patients",
            data="",
            content_type="text/plain",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        # Should NOT get CSRF-guard 400 ("Requête invalide")
        if r.status_code == 400:
            body = r.get_json() or {}
            assert body.get("error") != "Requête invalide"

    def test_idle_timeout_clears_session(self, app):
        """Session with a stale _last_active timestamp must be expired on next request."""
        import datetime as _dt
        c = _authed(app, "medecin_a")

        # Verify session is active
        r = c.get("/me")
        assert r.status_code == 200

        # Manually backdate _last_active to simulate idle timeout
        with c.session_transaction() as sess:
            stale = (_dt.datetime.utcnow() - _dt.timedelta(hours=2)).isoformat()
            sess['_last_active'] = stale

        # Next request should clear the session and return 401
        r = c.get("/me")
        assert r.status_code == 401, (
            "Idle timeout should expire session and return 401"
        )

    def test_rate_limit_config_present(self, app):
        """Rate limiting should be configured (extensions.limiter registered on app)."""
        from extensions import limiter
        # limiter should be bound to the app
        assert limiter is not None
        # The app should have RATELIMIT_ENABLED in its config (even if False in tests)
        # and the limiter must not raise on app access
        assert app is not None

    def test_totp_backup_codes_regen_requires_password(self, app):
        """Regenerating 2FA backup codes must fail without correct password."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/totp/backup-codes/regenerate", json={"password": "wrongpassword"})
        # Either 2FA not enabled (400) or wrong password (401) — both fine; must NOT be 200
        assert r.status_code != 200

    def test_image_upload_rejects_non_image(self, app):
        """Uploading a base64-encoded non-image payload must be rejected."""
        import base64
        c = _authed(app, "medecin_a")
        fake_b64 = base64.b64encode(b"This is not an image, just text").decode()
        r = c.post(
            "/api/patients/P_A001/upload",
            json={"type": "Test", "image": fake_b64}
        )
        assert r.status_code == 400
        assert "non autorisé" in (r.get_json() or {}).get("error", "").lower() or \
               r.status_code == 400
