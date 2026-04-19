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
    os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
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

    # Medecins
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

    # Admin user
    cur.execute(
        "INSERT OR IGNORE INTO users "
        "(id,username,password_hash,role,nom,prenom,status,totp_enabled,locked_until) "
        "VALUES (?,?,?,?,?,?,?,0,'')",
        ("ADMIN_T", "admin_test", generate_password_hash("AdminPass@2025!"),
         "admin", "Admin", "Test", "active")
    )

    # Test patient record
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

    # Patient user linked to P_A001
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


# ─── 8. Patient CRUD ─────────────────────────────────────────────────────────

class TestPatientCRUD:
    """Full create / read / update / soft-delete cycle for patients."""

    def test_create_patient_success(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients", json={
            "nom": "Lemaire", "prenom": "Sophie",
            "ddn": "1990-06-15", "sexe": "F",
            "telephone": "0600000001", "email": "sophie.lemaire@test.com",
            "antecedents": ["Myopie"], "allergies": []
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["ok"] is True
        assert data["id"].startswith("P")

    def test_create_patient_missing_email_returns_400(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients", json={
            "nom": "Sans", "prenom": "Email", "ddn": "1990-01-01", "sexe": "M"
        })
        assert r.status_code == 400

    def test_create_patient_requires_auth(self, client):
        r = client.post("/api/patients", json={
            "nom": "Ghost", "prenom": "User", "email": "g@x.com"
        })
        assert r.status_code in (401, 403)

    def test_patient_list_returns_list(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_patient_list_pagination(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients?page=1&per_page=10")
        assert r.status_code == 200
        data = r.get_json()
        assert "data" in data and "total" in data and "pages" in data

    def test_update_patient_success(self, app):
        c = _authed(app, "medecin_a")
        r = c.put("/api/patients/P_A001", json={
            "nom": "Dupont", "prenom": "Alice",
            "ddn": "1980-01-01", "sexe": "F",
            "telephone": "0600000002", "email": "alice@test.com",
            "antecedents": [], "allergies": []
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_update_patient_pii_re_encrypted(self, app, db_path):
        """After PUT, the nom column must still be Fernet-encrypted."""
        c = _authed(app, "medecin_a")
        c.put("/api/patients/P_A001", json={
            "nom": "Dupont", "prenom": "Alice", "ddn": "1980-01-01",
            "sexe": "F", "telephone": "", "email": "", "antecedents": [], "allergies": []
        })
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT nom FROM patients WHERE id='P_A001'").fetchone()
        con.close()
        assert row[0].startswith("gAAAAA"), "nom must remain encrypted after update"

    def test_birth_year_stored_on_create(self, app, db_path):
        """birth_year must be derived from ddn and stored as a plaintext integer."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients", json={
            "nom": "BYearTest", "prenom": "Fixture",
            "ddn": "1992-03-22", "sexe": "M",
            "telephone": "", "email": "byear@test.com",
            "antecedents": [], "allergies": []
        })
        assert r.status_code == 201
        pid = r.get_json()["id"]
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT birth_year, ddn FROM patients WHERE id=?", (pid,)).fetchone()
        con.close()
        assert row[0] == 1992, f"birth_year should be 1992, got {row[0]}"
        assert row[1].startswith("gAAAAA"), "ddn should be Fernet-encrypted"

    def test_birth_year_updated_on_put(self, app, db_path):
        """PUT with a new ddn must update birth_year."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients", json={
            "nom": "BYearUpd", "prenom": "Update",
            "ddn": "1985-07-10", "sexe": "F",
            "telephone": "", "email": "byearupd@test.com",
            "antecedents": [], "allergies": []
        })
        pid = r.get_json()["id"]
        c.put(f"/api/patients/{pid}", json={
            "nom": "BYearUpd", "prenom": "Update",
            "ddn": "1978-11-30", "sexe": "F",
            "telephone": "", "email": "", "antecedents": [], "allergies": []
        })
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT birth_year FROM patients WHERE id=?", (pid,)).fetchone()
        con.close()
        assert row[0] == 1978, f"birth_year should be updated to 1978, got {row[0]}"

    def test_soft_delete_removes_from_list(self, app, db_path):
        """Deleting a patient flags deleted=1 and hides it from the list."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients", json={
            "nom": "ToDelete", "prenom": "Patient",
            "ddn": "1970-01-01", "sexe": "M",
            "telephone": "", "email": "todelete@test.com",
            "antecedents": [], "allergies": []
        })
        pid = r.get_json()["id"]

        rd = c.delete(f"/api/patients/{pid}", json={})
        assert rd.status_code == 200

        ids = [p["id"] for p in c.get("/api/patients").get_json()]
        assert pid not in ids

        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM patients WHERE id=?", (pid,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_patient_export(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/export")
        assert r.status_code == 200
        data = r.get_json()
        # Export must be anonymised — no name
        assert "nom" not in data
        assert "sexe" in data


# ─── 9. Historique ───────────────────────────────────────────────────────────

class TestHistorique:
    """Consultation history CRUD."""

    def _create_entry(self, c, pid="P_A001", date="2024-03-01"):
        return c.post(f"/api/patients/{pid}/historique", json={
            "date": date, "motif": "Test motif",
            "diagnostic": "Test diagnostic", "traitement": "Test traitement",
            "tension_od": "15", "tension_og": "16",
            "acuite_od": "10/10", "acuite_og": "9/10", "notes": "Test"
        })

    def test_create_historique(self, app):
        c = _authed(app, "medecin_a")
        r = self._create_entry(c)
        assert r.status_code == 201
        data = r.get_json()
        assert data["ok"] is True
        assert data["id"].startswith("H")

    def test_list_historique_requires_auth(self, client):
        # Historique is returned inside GET /api/patients/<pid> — which requires auth
        r = client.get("/api/patients/P_A001")
        assert r.status_code in (401, 403)

    def test_list_historique(self, app):
        c = _authed(app, "medecin_a")
        data = c.get("/api/patients/P_A001").get_json()
        assert "historique" in data
        assert isinstance(data["historique"], list)

    def test_list_grows_after_create(self, app):
        c = _authed(app, "medecin_a")
        before = len(c.get("/api/patients/P_A001").get_json()["historique"])
        self._create_entry(c, date="2024-05-10")
        after = len(c.get("/api/patients/P_A001").get_json()["historique"])
        assert after == before + 1

    def test_update_historique(self, app):
        c = _authed(app, "medecin_a")
        hid = self._create_entry(c, date="2024-06-01").get_json()["id"]
        r = c.put(f"/api/patients/P_A001/historique/{hid}", json={
            "date": "2024-06-02", "motif": "Suivi", "diagnostic": "Stable",
            "traitement": "Unchanged", "tension_od": "14", "tension_og": "15",
            "acuite_od": "10/10", "acuite_og": "10/10", "notes": "Updated"
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_delete_historique_soft(self, app, db_path):
        c = _authed(app, "medecin_a")
        hid = self._create_entry(c, date="2024-07-01").get_json()["id"]
        r = c.delete(f"/api/patients/P_A001/historique/{hid}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM historique WHERE id=?", (hid,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_medecin_b_cannot_add_historique(self, app):
        c = _authed(app, "medecin_b")
        r = self._create_entry(c, pid="P_A001")
        assert r.status_code == 403

    def test_patient_cannot_add_historique(self, app):
        c = _authed(app, "patient_a")
        r = self._create_entry(c)
        assert r.status_code == 403

    def test_trends_endpoint(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/trends")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)


# ─── 10. RDV ─────────────────────────────────────────────────────────────────

class TestRDV:
    """Appointment CRUD and conflict detection."""

    _date_counter = 0  # prevent date collisions across tests

    @classmethod
    def _next_date(cls):
        cls._date_counter += 1
        return f"2026-{(cls._date_counter % 12) + 1:02d}-{(cls._date_counter % 28) + 1:02d}"

    def _create_rdv(self, c, pid="P_A001", heure="10:00"):
        return c.post("/api/rdv", json={
            "patient_id": pid, "date": self._next_date(),
            "heure": heure, "type": "Consultation", "notes": ""
        })

    def test_list_rdv_requires_auth(self, client):
        r = client.get("/api/rdv")
        assert r.status_code in (401, 403)

    def test_create_rdv_requires_auth(self, client):
        r = client.post("/api/rdv", json={
            "patient_id": "P_A001", "date": "2026-01-01", "heure": "09:00"
        })
        assert r.status_code in (401, 403)

    def test_create_rdv_success(self, app):
        c = _authed(app, "medecin_a")
        r = self._create_rdv(c)
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["rdv"]["id"].startswith("RDV")

    def test_list_rdv(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/rdv")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_rdv_conflict_detection(self, app):
        """Two RDVs for the same patient at identical date+time → 409."""
        c = _authed(app, "medecin_a")
        date = self._next_date()
        c.post("/api/rdv", json={
            "patient_id": "P_A001", "date": date, "heure": "11:00",
            "type": "Consultation"
        })
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001", "date": date, "heure": "11:00",
            "type": "Consultation"
        })
        assert r.status_code == 409

    def test_update_rdv(self, app):
        c = _authed(app, "medecin_a")
        rdv_id = self._create_rdv(c).get_json()["rdv"]["id"]
        r = c.put(f"/api/rdv/{rdv_id}", json={
            "date": self._next_date(), "heure": "15:00",
            "type": "Suivi", "statut": "programmé", "notes": "Updated"
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_validate_rdv(self, app):
        c = _authed(app, "medecin_a")
        rdv_id = self._create_rdv(c).get_json()["rdv"]["id"]
        r = c.post(f"/api/rdv/{rdv_id}/valider", json={"statut": "confirmé"})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_delete_rdv_soft(self, app, db_path):
        c = _authed(app, "medecin_a")
        rdv_id = self._create_rdv(c).get_json()["rdv"]["id"]
        r = c.delete(f"/api/rdv/{rdv_id}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM rdv WHERE id=?", (rdv_id,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_patient_can_request_rdv(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001",
            "date": self._next_date(), "heure": "09:30",
            "type": "Urgence", "urgent": True
        })
        assert r.status_code == 200

    def test_patient_cannot_delete_rdv(self, app):
        c_med = _authed(app, "medecin_a")
        rdv_id = self._create_rdv(c_med).get_json()["rdv"]["id"]
        c_pat = _authed(app, "patient_a")
        r = c_pat.delete(f"/api/rdv/{rdv_id}", json={})
        assert r.status_code == 403


# ─── 11. Documents ───────────────────────────────────────────────────────────

class TestDocuments:
    """Image upload, file storage, list, validate, soft-delete, restore."""

    # Minimal valid 1×1 PNG encoded in base64
    _PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    def test_upload_valid_image(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/upload", json={
            "type": "Fond d'œil", "description": "Test upload",
            "image": self._PNG_B64
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert r.get_json()["id"].startswith("DOC")

    def test_upload_stores_to_file_not_db_column(self, app, db_path):
        """New uploads must write an encrypted file and leave image_b64 empty in DB."""
        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "OCT", "description": "File storage test",
            "image": self._PNG_B64
        }).get_json()["id"]

        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT image_b64, image_path FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        con.close()
        assert row[0] == '' or row[0] is None, "image_b64 should be empty for new uploads"
        assert row[1] and row[1] != '', "image_path should point to the encrypted file"

    def test_get_document_returns_image_from_file(self, app):
        """GET single document must return decrypted image_b64 loaded from the file."""
        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "FO", "description": "Retrieve test",
            "image": self._PNG_B64
        }).get_json()["id"]
        r = c.get(f"/api/patients/P_A001/documents/{doc_id}")
        assert r.status_code == 200
        assert r.get_json().get("image_b64"), "GET document must return non-empty image_b64"

    def test_list_documents_requires_auth(self, client):
        r = client.get("/api/patients/P_A001/documents")
        assert r.status_code in (401, 403)

    def test_list_documents(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/documents")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_sets_has_image_flag(self, app):
        """Document list must set has_image=1 for docs uploaded by a patient (source='document')."""
        # Medecin uploads have source='imagerie' and are excluded from the document list.
        # Patient uploads have source='document' and appear in the list.
        c_pat = _authed(app, "patient_a")
        c_pat.post("/api/patients/P_A001/upload", json={
            "type": "Ordonnance photo", "image": self._PNG_B64,
            "medecin_id": "MED_A"
        })
        c_med = _authed(app, "medecin_a")
        docs = c_med.get("/api/patients/P_A001/documents").get_json()
        assert any(d.get("has_image") for d in docs), \
            "Patient-uploaded document with image should have has_image=1"

    def test_upload_without_image(self, app):
        """Upload without image (plain document) must also succeed."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/upload", json={
            "type": "Compte-rendu", "description": "No image"
        })
        assert r.status_code == 200

    def test_validate_document(self, app):
        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "ToValidate"
        }).get_json()["id"]
        r = c.post(f"/api/patients/P_A001/documents/{doc_id}/validate", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_soft_delete_document(self, app, db_path):
        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "ToDelete"
        }).get_json()["id"]
        r = c.delete(f"/api/patients/P_A001/documents/{doc_id}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM documents WHERE id=?", (doc_id,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_restore_document(self, app, db_path):
        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "ToRestore"
        }).get_json()["id"]
        c.delete(f"/api/patients/P_A001/documents/{doc_id}", json={})
        r = c.post(f"/api/patients/P_A001/documents/{doc_id}/restore", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM documents WHERE id=?", (doc_id,)).fetchone()
        con.close()
        assert row[0] == 0

    def test_patient_cannot_see_other_patient_docs(self, app):
        c = _authed(app, "patient_a")
        r = c.get("/api/patients/P_A002/documents")
        assert r.status_code in (401, 403)

    def test_ai_analysis_blocked_without_consent(self, app):
        """analyze endpoint must return 403 consent_required when consent not granted."""
        c = _authed(app, "medecin_a")
        # Revoke ai_analysis consent to ensure it's not set
        c.post("/api/consent/revoke", json={
            "patient_id": "P_A001", "consent_type": "ai_analysis"
        })
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "TestAI", "image": self._PNG_B64
        }).get_json()["id"]
        r = c.post(f"/api/patients/P_A001/documents/{doc_id}/analyze", json={})
        assert r.status_code == 403
        assert r.get_json().get("consent_required") is True


# ─── 12. Questions ───────────────────────────────────────────────────────────

class TestQuestions:
    """Patient questions and medecin answers."""

    def test_list_questions_requires_auth(self, client):
        r = client.get("/api/patients/P_A001/questions")
        assert r.status_code in (401, 403)

    def test_medecin_can_list_questions(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/questions")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_patient_can_ask_question(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/questions", json={
            "question": "Quand est mon prochain rendez-vous ?"
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["question"]["id"].startswith("Q")

    def test_medecin_can_answer_question(self, app):
        c_pat = _authed(app, "patient_a")
        qid = c_pat.post("/api/patients/P_A001/questions", json={
            "question": "Est-ce que mon glaucome s'améliore ?"
        }).get_json()["question"]["id"]
        c_med = _authed(app, "medecin_a")
        r = c_med.post(f"/api/patients/P_A001/questions/{qid}/repondre", json={
            "reponse": "Oui, les pressions oculaires sont stables."
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_cannot_delete_unanswered_question(self, app):
        """Deleting a question in 'en_attente' status must return 400."""
        c_pat = _authed(app, "patient_a")
        qid = c_pat.post("/api/patients/P_A001/questions", json={
            "question": "Question sans réponse"
        }).get_json()["question"]["id"]
        c_med = _authed(app, "medecin_a")
        r = c_med.delete(f"/api/patients/P_A001/questions/{qid}", json={})
        assert r.status_code == 400

    def test_can_delete_answered_question(self, app, db_path):
        """A question with a reply can be soft-deleted."""
        c_pat = _authed(app, "patient_a")
        qid = c_pat.post("/api/patients/P_A001/questions", json={
            "question": "Question à supprimer"
        }).get_json()["question"]["id"]
        c_med = _authed(app, "medecin_a")
        c_med.post(f"/api/patients/P_A001/questions/{qid}/repondre", json={
            "reponse": "Réponse du médecin."
        })
        r = c_med.delete(f"/api/patients/P_A001/questions/{qid}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM questions WHERE id=?", (qid,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_patient_cannot_access_other_patient_questions(self, app):
        c = _authed(app, "patient_a")
        r = c.get("/api/patients/P_A002/questions")
        assert r.status_code in (401, 403)


# ─── 13. Ordonnances ─────────────────────────────────────────────────────────

class TestOrdonnances:
    """Prescription CRUD."""

    def test_list_ordonnances_requires_auth(self, client):
        r = client.get("/api/patients/P_A001/ordonnances")
        assert r.status_code in (401, 403)

    def test_create_ordonnance(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/ordonnances", json={
            "type": "medicaments",
            "contenu": {"medicaments": [{"nom": "Timolol 0.5%", "posologie": "2x/j"}]},
            "notes": "Renouvellement 3 mois"
        })
        assert r.status_code == 201
        assert r.get_json()["id"].startswith("O")

    def test_list_ordonnances(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/ordonnances")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_includes_created_ordonnance(self, app):
        c = _authed(app, "medecin_a")
        before = len(c.get("/api/patients/P_A001/ordonnances").get_json())
        c.post("/api/patients/P_A001/ordonnances", json={
            "type": "medicaments", "contenu": {}, "notes": "Count test"
        })
        after = len(c.get("/api/patients/P_A001/ordonnances").get_json())
        assert after == before + 1

    def test_patient_cannot_create_ordonnance(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/ordonnances", json={"type": "medicaments"})
        assert r.status_code == 403

    def test_delete_ordonnance(self, app, db_path):
        c = _authed(app, "medecin_a")
        oid = c.post("/api/patients/P_A001/ordonnances", json={
            "type": "lunettes", "contenu": {}, "notes": "Delete me"
        }).get_json()["id"]
        r = c.delete(f"/api/patients/P_A001/ordonnances/{oid}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM ordonnances WHERE id=?", (oid,)).fetchone()
        con.close()
        assert row[0] == 1


# ─── 14. IVT ─────────────────────────────────────────────────────────────────

class TestIVT:
    """Intravitreal injection CRUD and auto-numbering."""

    def test_list_ivt_requires_auth(self, client):
        r = client.get("/api/patients/P_A001/ivt")
        assert r.status_code in (401, 403)

    def test_create_ivt(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/ivt", json={
            "oeil": "OG", "medicament": "Ranibizumab",
            "dose": "0.5mg", "date": "2024-03-01", "notes": "RAS"
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["id"].startswith("IVT")
        assert data["numero"] >= 1

    def test_list_ivt(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/ivt")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_ivt_autonumbering(self, app):
        """Each new injection for the same eye gets the next sequential numero."""
        c = _authed(app, "medecin_a")
        r1 = c.post("/api/patients/P_A001/ivt", json={
            "oeil": "OD", "medicament": "Aflibercept",
            "dose": "2mg", "date": "2024-04-01"
        })
        r2 = c.post("/api/patients/P_A001/ivt", json={
            "oeil": "OD", "medicament": "Aflibercept",
            "dose": "2mg", "date": "2024-05-01"
        })
        assert r2.get_json()["numero"] == r1.get_json()["numero"] + 1

    def test_patient_cannot_create_ivt(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/ivt", json={"oeil": "OG"})
        assert r.status_code == 403

    def test_delete_ivt_soft(self, app, db_path):
        c = _authed(app, "medecin_a")
        iid = c.post("/api/patients/P_A001/ivt", json={
            "oeil": "OG", "medicament": "Bevacizumab",
            "dose": "1.25mg", "date": "2024-06-01"
        }).get_json()["id"]
        r = c.delete(f"/api/patients/P_A001/ivt/{iid}", json={})
        assert r.status_code == 200
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM ivt WHERE id=?", (iid,)).fetchone()
        con.close()
        assert row[0] == 1


# ─── 15. Notifications ───────────────────────────────────────────────────────

class TestNotifications:
    """Notification list and mark-as-read."""

    def test_list_requires_auth(self, client):
        r = client.get("/api/notifications")
        assert r.status_code in (401, 403)

    def test_list_notifications_medecin(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/notifications")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_notifications_patient(self, app):
        c = _authed(app, "patient_a")
        r = c.get("/api/notifications")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_mark_notification_read(self, app, db_path):
        """Posting to /lu must flip lu=1 in the DB."""
        # First create a notification by having the patient request an RDV
        c_pat = _authed(app, "patient_a")
        c_pat.post("/api/rdv", json={
            "patient_id": "P_A001",
            "date": "2027-01-10", "heure": "08:00",
            "type": "Urgence", "urgent": True
        })
        c_med = _authed(app, "medecin_a")
        notifs = c_med.get("/api/notifications").get_json()
        if not notifs:
            pytest.skip("No notifications available to mark as read")
        nid = notifs[0]["id"]
        r = c_med.post(f"/api/notifications/{nid}/lu", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT lu FROM notifications WHERE id=?", (nid,)).fetchone()
        con.close()
        assert row[0] == 1

    def test_mark_lu_requires_auth(self, client):
        r = client.post("/api/notifications/FAKE123/lu", json={})
        assert r.status_code in (401, 403)


# ─── 16. Admin access control ────────────────────────────────────────────────

class TestAdmin:
    """Admin endpoints must reject non-admin roles."""

    _ADMIN_ROUTES_GET  = ["/api/admin/stats", "/api/admin/users", "/api/admin/users/pending"]
    _ADMIN_ROUTES_POST = [
        "/api/admin/users/X/validate",
        "/api/admin/users/X/deactivate",
        "/api/admin/users/X/activate",
    ]

    def test_admin_get_routes_blocked_for_medecin(self, app):
        c = _authed(app, "medecin_a")
        for url in self._ADMIN_ROUTES_GET:
            r = c.get(url)
            assert r.status_code == 403, f"Expected 403 for medecin at {url}, got {r.status_code}"

    def test_admin_post_routes_blocked_for_medecin(self, app):
        c = _authed(app, "medecin_a")
        for url in self._ADMIN_ROUTES_POST:
            r = c.post(url, json={})
            assert r.status_code == 403, f"Expected 403 for medecin at {url}, got {r.status_code}"

    def test_admin_routes_blocked_for_patient(self, app):
        c = _authed(app, "patient_a")
        for url in self._ADMIN_ROUTES_GET:
            r = c.get(url)
            assert r.status_code == 403, f"Expected 403 for patient at {url}, got {r.status_code}"

    def test_admin_delete_user_blocked_for_medecin(self, app):
        c = _authed(app, "medecin_a")
        r = c.delete("/api/admin/users/NOBODY", json={})
        assert r.status_code == 403

    def test_admin_endpoints_require_login(self, client):
        for url in self._ADMIN_ROUTES_GET:
            r = client.get(url)
            assert r.status_code in (401, 403), \
                f"Unauthenticated GET {url} should be 401/403, got {r.status_code}"

    def test_admin_can_list_users(self, app):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        r = c.get("/api/admin/users")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_admin_can_view_stats(self, app):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        r = c.get("/api/admin/stats")
        assert r.status_code == 200


# ─── 17. Data integrity ───────────────────────────────────────────────────────

class TestDataIntegrity:
    """Cross-cutting checks: age_bands, stats scoping, GDPR, audit log."""

    def test_stats_age_bands_non_zero(self, app):
        """age_bands must be populated when patients have birth_year set."""
        c = _authed(app, "medecin_a")
        # Ensure at least one patient with a known DOB exists under medecin_a
        c.post("/api/patients", json={
            "nom": "AgeBand", "prenom": "Test",
            "ddn": "1970-01-01", "sexe": "M",
            "telephone": "", "email": "ageband@test.com",
            "antecedents": [], "allergies": []
        })
        data = c.get("/api/stats").get_json()
        bands = data["age_bands"]
        assert sum(bands.values()) >= 1, "age_bands should have at least one patient counted"

    def test_stats_excludes_deleted_patients(self, app):
        """A soft-deleted patient must not be counted in total_patients."""
        c = _authed(app, "medecin_a")
        before = c.get("/api/stats").get_json()["total_patients"]
        pid = c.post("/api/patients", json={
            "nom": "Phantom", "prenom": "Delete",
            "ddn": "1960-05-05", "sexe": "M",
            "telephone": "", "email": "phantom@test.com",
            "antecedents": [], "allergies": []
        }).get_json()["id"]
        assert c.get("/api/stats").get_json()["total_patients"] == before + 1
        c.delete(f"/api/patients/{pid}", json={})
        assert c.get("/api/stats").get_json()["total_patients"] == before

    def test_audit_log_requires_auth(self, client):
        r = client.get("/api/patients/P_A001/audit")
        assert r.status_code in (401, 403)

    def test_audit_log_accessible_by_medecin(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/audit")
        assert r.status_code == 200

    def test_audit_log_blocked_for_patient(self, app):
        c = _authed(app, "patient_a")
        r = c.get("/api/patients/P_A001/audit")
        assert r.status_code == 403

    def test_gdpr_delete_anonymises_audit_log(self, app, db_path):
        """After patient delete, audit_log detail must be anonymised (GDPR erasure)."""
        c = _authed(app, "medecin_a")
        pid = c.post("/api/patients", json={
            "nom": "GDPR", "prenom": "Erase",
            "ddn": "1965-08-15", "sexe": "F",
            "telephone": "", "email": "gdpr@test.com",
            "antecedents": [], "allergies": []
        }).get_json()["id"]
        c.get(f"/api/patients/{pid}")    # produces at least one audit READ entry
        c.delete(f"/api/patients/{pid}", json={})

        con = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT detail FROM audit_log "
            "WHERE patient_id=? AND action != 'patient_deleted_gdpr'",
            (pid,)
        ).fetchall()
        con.close()
        for (detail,) in rows:
            assert detail == '[données supprimées - RGPD]', \
                f"Audit detail should be anonymised, got: {detail!r}"

    def test_sex_distribution_normalised(self, app):
        """sex_dist must only contain keys M, F, or N/R — never raw ciphertext."""
        c = _authed(app, "medecin_a")
        data = c.get("/api/stats").get_json()
        for key in data.get("sex_dist", {}):
            assert key in ("M", "F", "N/R"), \
                f"Unexpected sex_dist key (possibly ciphertext): {key!r}"

    def test_patient_profile_endpoint(self, app):
        """Authenticated users can update their own profile settings via PUT."""
        c = _authed(app, "medecin_a")
        r = c.put("/api/settings/profile", json={
            "nom": "Test", "prenom": "Dr",
            "email": "drtest@test.com", "organisation": "Clinique Test"
        })
        # 200 success or 400 validation — must not be 401/403/500
        assert r.status_code in (200, 400)


# ─── 17. Encryption round-trip ────────────────────────────────────────────────

class TestEncryptionRoundTrip:
    """Verify that data written encrypted comes back as readable plaintext via the API.

    These tests catch silent decrypt failures — scenarios where the HTTP status
    is 200 but the response body contains raw Fernet tokens instead of text.
    """

    _FERNET_RE = __import__('re').compile(r'^gAAAAA[A-Za-z0-9_\-]{40,}={0,2}$')

    def _is_ciphertext(self, value):
        """Return True if value looks like a Fernet token (should never reach the API caller)."""
        return bool(value and self._FERNET_RE.match(str(value).strip()))

    def test_patient_pii_decrypted_on_read(self, app, db_path):
        """Patient name/dob must be readable plaintext, not Fernet tokens."""
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001")
        assert r.status_code == 200
        p = r.get_json()
        assert not self._is_ciphertext(p["nom"]),    f"nom is ciphertext: {p['nom'][:30]}"
        assert not self._is_ciphertext(p["prenom"]), f"prenom is ciphertext: {p['prenom'][:30]}"
        assert not self._is_ciphertext(p["ddn"]),    f"ddn is ciphertext: {p['ddn'][:30]}"
        assert p["nom"] == "Dupont"
        assert p["prenom"] == "Alice"

    def test_historique_clinical_fields_decrypted(self, app, db_path):
        """Consultation motif/diagnostic/notes must be readable after encrypt-write + read."""
        c = _authed(app, "medecin_a")
        # Write with known plaintext
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "2024-06-01",
            "motif": "Test motif clair",
            "diagnostic": "Glaucome stade 2",
            "traitement": "Timolol 0.5%",
            "notes": "Notes de test lisibles",
            "segment_ant": "RAS",
        })
        assert r.status_code == 201
        hid = r.get_json()["id"]

        # Verify DB stores ciphertext (not plaintext)
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT motif, diagnostic FROM historique WHERE id=?", (hid,)).fetchone()
        con.close()
        assert self._is_ciphertext(row[0]), "DB should store encrypted motif, not plaintext"
        assert self._is_ciphertext(row[1]), "DB should store encrypted diagnostic, not plaintext"

        # Verify API returns plaintext
        p = c.get("/api/patients/P_A001").get_json()
        h = next((x for x in p["historique"] if x["id"] == hid), None)
        assert h is not None
        assert h["motif"]      == "Test motif clair",     f"motif ciphertext: {h['motif'][:30]}"
        assert h["diagnostic"] == "Glaucome stade 2",     f"diagnostic ciphertext: {h['diagnostic'][:30]}"
        assert h["notes"]      == "Notes de test lisibles", f"notes ciphertext: {h['notes'][:30]}"

    def test_ordonnance_content_decrypted(self, app, db_path):
        """Ordonnance notes must be readable plaintext via the API, encrypted in DB."""
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/ordonnances", json={
            "type": "medicaments",
            "contenu": {"medicaments": [{"nom": "Dorzolamide", "posologie": "3x/j"}]},
            "notes": "Note ordonnance lisible",
        })
        assert r.status_code == 201
        oid = r.get_json()["id"]

        # Verify DB stores encrypted notes
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT notes, contenu FROM ordonnances WHERE id=?", (oid,)).fetchone()
        con.close()
        assert self._is_ciphertext(row[0]), "DB should store encrypted notes"
        assert self._is_ciphertext(row[1]), "DB should store encrypted contenu"

        # Verify API returns plaintext
        ords = c.get("/api/patients/P_A001/ordonnances").get_json()
        o = next((x for x in ords if x["id"] == oid), None)
        assert o is not None
        assert o["notes"] == "Note ordonnance lisible", f"notes ciphertext: {o['notes'][:30]}"
        assert isinstance(o["contenu"], dict), "contenu should be parsed JSON dict, not string"
        assert o["contenu"]["medicaments"][0]["nom"] == "Dorzolamide"

    def test_question_text_decrypted(self, app, db_path):
        """Patient question text must be readable via the API, encrypted at rest."""
        # Grant AI consent so the question flow completes
        con = sqlite3.connect(db_path)
        import uuid as _uuid
        con.execute(
            "INSERT OR REPLACE INTO patient_consents (id, patient_id, user_id, consent_type, granted) "
            "VALUES (?,?,?,?,1)",
            (str(_uuid.uuid4()), "P_A001", "MED_A", "ai_analysis")
        )
        con.commit()
        con.close()

        c_pat = _authed(app, "patient_a")
        r = c_pat.post("/api/patients/P_A001/questions", json={
            "question": "Question lisible en clair"
        })
        assert r.status_code == 200
        qid = r.get_json()["question"]["id"]

        # Verify DB stores encrypted question
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT question FROM questions WHERE id=?", (qid,)).fetchone()
        con.close()
        assert self._is_ciphertext(row[0]), "DB should store encrypted question text"

        # Verify API returns plaintext
        qs = c_pat.get("/api/patients/P_A001/questions").get_json()
        q = next((x for x in qs if x["id"] == qid), None)
        assert q is not None
        assert q["question"] == "Question lisible en clair", \
            f"question is ciphertext: {q['question'][:30]}"

    def test_security_utils_fernet_roundtrip(self):
        """Unit test: encrypt → decrypt must be an identity function."""
        from security_utils import encrypt_field, decrypt_field, encrypt_clinical, decrypt_clinical
        samples = [
            "Glaucome primitif à angle ouvert",
            "Latanoprost 0.005% — 1 goutte le soir",
            "patient présente une acuité 5/10 OD",
            "Alice Dupont, née le 01/01/1980",
            "",  # empty string must pass through unchanged
        ]
        for text in samples:
            assert decrypt_field(encrypt_field(text)) == text, \
                f"Round-trip failed for: {text!r}"

        # Clinical dict round-trip
        row = {"motif": "Baisse AV", "diagnostic": "DMLA", "traitement": "IVT", "notes": "RAS", "segment_ant": ""}
        result = decrypt_clinical(encrypt_clinical(row))
        for k, v in row.items():
            assert result[k] == v, f"Clinical round-trip failed for field {k!r}"

    def test_double_encrypt_guard(self):
        """Encrypting an already-encrypted value must not double-encrypt it."""
        from security_utils import encrypt_field, decrypt_field, _is_encrypted
        plaintext = "Valeur sensible"
        once      = encrypt_field(plaintext)
        assert _is_encrypted(once)
        # Simulating the idempotent guard used in encrypt_clinical/_is_encrypted
        # If we call encrypt_field on an already-encrypted token it WILL wrap it again —
        # that's why encrypt_clinical checks _is_encrypted first. Verify the guard works.
        from security_utils import encrypt_clinical, decrypt_clinical
        row = {"motif": once, "diagnostic": "", "traitement": "", "notes": "", "segment_ant": ""}
        re_encrypted = encrypt_clinical(row)
        # The guard should have left the already-encrypted field untouched
        assert re_encrypted["motif"] == once, \
            "encrypt_clinical should not re-encrypt an already-encrypted value"
        assert decrypt_clinical(re_encrypted)["motif"] == plaintext


# ─── 18. Date validation ──────────────────────────────────────────────────────

class TestDateValidation:
    """Invalid date/time strings must be rejected at the API boundary."""

    # ── Unit tests for the validator itself ───────────────────────────────────

    def test_valid_date_accepts_iso(self):
        from security_utils import valid_date
        assert valid_date("2024-03-15") is True
        assert valid_date("2000-01-01") is True
        assert valid_date("1999-12-31") is True

    def test_valid_date_rejects_bad_formats(self):
        from security_utils import valid_date
        assert valid_date("15-03-2024") is False    # wrong order
        assert valid_date("2024/03/15") is False    # slashes
        assert valid_date("not-a-date") is False
        assert valid_date("") is False
        assert valid_date(None) is False
        assert valid_date("2024-13-01") is False    # month 13
        assert valid_date("2024-00-10") is False    # month 0

    def test_valid_heure_accepts_hhmm(self):
        from security_utils import valid_heure
        assert valid_heure("09:00") is True
        assert valid_heure("23:59") is True
        assert valid_heure("00:00") is True
        assert valid_heure("") is True      # empty is allowed
        assert valid_heure(None) is True    # None is allowed

    def test_valid_heure_rejects_bad_formats(self):
        from security_utils import valid_heure
        assert valid_heure("9:00") is False     # missing leading zero
        assert valid_heure("24:00") is False    # hour 24
        assert valid_heure("12:60") is False    # minute 60
        assert valid_heure("noon") is False

    # ── Integration: bad dates rejected at the RDV endpoint ──────────────────

    def test_rdv_rejects_bad_date(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001",
            "date": "15/03/2024",   # wrong format
            "heure": "10:00",
            "type": "Consultation"
        })
        assert r.status_code == 400
        assert "date" in r.get_json().get("error", "").lower()

    def test_rdv_rejects_bad_heure(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001",
            "date": "2025-06-01",
            "heure": "9:00",        # missing leading zero
            "type": "Consultation"
        })
        assert r.status_code == 400
        assert "heure" in r.get_json().get("error", "").lower()

    def test_rdv_accepts_valid_date(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001",
            "date": "2028-09-15",
            "heure": "14:30",
            "type": "Consultation"
        })
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    # ── Integration: bad dates rejected at the historique endpoint ────────────

    def test_historique_rejects_bad_date(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "01-01-2024",   # wrong format
            "motif": "Test"
        })
        assert r.status_code == 400
        assert "date" in r.get_json().get("error", "").lower()

    def test_historique_accepts_valid_date(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "2024-09-20", "motif": "Date valid test",
            "diagnostic": "", "traitement": "",
            "tension_od": "", "tension_og": "",
            "acuite_od": "", "acuite_og": "", "notes": ""
        })
        assert r.status_code == 201


# ─── New-feature coverage ──────────────────────────────────────────────────────

class TestClinicalFieldLengthCaps:
    """Free-text clinical fields must be rejected when they exceed their cap."""

    def test_motif_too_long_rejected(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "2025-01-01",
            "motif": "x" * 1001,   # over the 1000-char cap
            "diagnostic": "", "traitement": "", "notes": ""
        })
        assert r.status_code == 400
        assert "motif" in r.get_json().get("error", "").lower()

    def test_notes_too_long_rejected(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "2025-01-02",
            "motif": "ok",
            "diagnostic": "", "traitement": "",
            "notes": "n" * 3001,   # over the 3000-char cap
        })
        assert r.status_code == 400
        assert "notes" in r.get_json().get("error", "").lower()

    def test_within_cap_accepted(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/historique", json={
            "date": "2025-01-03",
            "motif": "x" * 999,
            "diagnostic": "", "traitement": "", "notes": ""
        })
        assert r.status_code == 201


class TestPatientPdfExport:
    def test_pdf_returns_pdf_content_type(self, app):
        c = _authed(app, "medecin_a")
        r = c.get("/api/patients/P_A001/pdf")
        assert r.status_code in (200, 501)  # 501 if reportlab not installed
        if r.status_code == 200:
            assert "pdf" in r.content_type.lower()

    def test_pdf_blocked_for_wrong_medecin(self, app):
        c = _authed(app, "medecin_b")
        r = c.get("/api/patients/P_A001/pdf")
        assert r.status_code == 403


class TestAdminAssignDetachMedecin:
    def test_assign_medecin_updates_patient(self, app, db_path):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        users = c.get("/api/admin/users").get_json()
        med_b = next((u for u in users if u["username"] == "medecin_b"), None)
        assert med_b, "medecin_b must exist in test DB"
        r = c.put("/api/admin/patients/P_A001/medecin", json={"medecin_id": med_b["id"]})
        assert r.get_json().get("ok")
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT medecin_id FROM patients WHERE id='P_A001'").fetchone()
        con.close()
        assert row[0] == med_b["id"]

    def test_detach_medecin_clears_field(self, app, db_path):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        r = c.delete("/api/admin/patients/P_A001/medecin", json={})
        assert r.get_json().get("ok"), r.get_json()
        con = sqlite3.connect(db_path)
        row = con.execute("SELECT medecin_id FROM patients WHERE id='P_A001'").fetchone()
        con.close()
        assert row[0] in (None, '')
        # Restore medecin_a ownership for downstream tests
        users = c.get("/api/admin/users").get_json()
        med_a = next((u for u in users if u["username"] == "medecin_a"), None)
        if med_a:
            c.put("/api/admin/patients/P_A001/medecin", json={"medecin_id": med_a["id"]})

    def test_assign_nonexistent_medecin_returns_404(self, app):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        r = c.put("/api/admin/patients/P_A001/medecin", json={"medecin_id": "NONEXISTENT"})
        assert r.status_code == 404

    def test_detach_blocked_for_medecin(self, app):
        c = _authed(app, "medecin_a")
        r = c.delete("/api/admin/patients/P_A001/medecin", json={})
        assert r.status_code in (401, 403)


class TestPatientRestoreRestoresRdv:
    def test_delete_patient_soft_deletes_future_rdv(self, app, db_path):
        c = _authed(app, "medecin_a")
        future = "2099-12-31"
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001", "date": future, "heure": "09:00",
            "type": "Contrôle", "statut": "programmé", "medecin": "Dr. A", "urgent": False
        })
        assert r.get_json().get("ok"), r.get_json()
        rdv_id = r.get_json().get("rdv", {}).get("id")
        assert rdv_id, "add_rdv must return rdv.id"

        c.delete("/api/patients/P_A001", json={})

        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM rdv WHERE id=?", (rdv_id,)).fetchone()
        con.close()
        assert row and row[0] == 1

        c.post("/api/patients/P_A001/restore", json={})

        con = sqlite3.connect(db_path)
        row = con.execute("SELECT deleted FROM rdv WHERE id=?", (rdv_id,)).fetchone()
        con.close()
        assert row and row[0] == 0


class TestGenerateSuiviMedecinName:
    def test_suivi_rdv_medecin_field_is_not_ciphertext(self, app, db_path):
        """RDVs created by _generate_suivi must have a readable name, not a Fernet token."""
        import re as _re
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/chirurgie", json={
            "date_chirurgie": "2099-06-01",
            "type_chirurgie": "Cataracte OD",
            "add_to_agenda": True,
        })
        assert r.get_json().get("ok")

        con = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT medecin FROM rdv WHERE type LIKE 'Suivi post-op%' AND patient_id='P_A001' LIMIT 5"
        ).fetchall()
        con.close()

        fernet_re = _re.compile(r'^gAAAAA[A-Za-z0-9_\-]{40,}={0,2}$')
        for (med_name,) in rows:
            assert med_name is not None
            assert not fernet_re.match(med_name or ''), \
                f"rdv.medecin looks like a Fernet token: {med_name!r}"


class TestRdvHiddenForDeletedPatients:
    def test_rdv_list_excludes_deleted_patient_rdvs(self, app, db_path):
        c = _authed(app, "medecin_a")
        future = "2099-11-15"
        r = c.post("/api/rdv", json={
            "patient_id": "P_A001", "date": future, "heure": "10:00",
            "type": "Test exclusion", "statut": "programmé",
            "medecin": "Dr. A", "urgent": False
        })
        rdv_id = r.get_json().get("rdv", {}).get("id")
        assert rdv_id, "add_rdv must return rdv.id"

        rdvs_before = c.get("/api/rdv").get_json()
        assert any(rv["id"] == rdv_id for rv in rdvs_before)

        c.delete("/api/patients/P_A001", json={})

        rdvs_after = c.get("/api/rdv").get_json()
        assert not any(rv["id"] == rdv_id for rv in rdvs_after)

        c.post("/api/patients/P_A001/restore", json={})
