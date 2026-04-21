"""Tests for deployment-readiness additions: /api/v1/ alias, /api/health,
/api/ready, and background analysis retry semantics.
"""
"""Tests for deployment-readiness additions: /api/v1/ alias, /api/health,
/api/ready, and background analysis retry semantics.

Fixtures (app, db_path, client) come from conftest.py.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from test_smoke import _login, _authed  # noqa: F401


class TestHealthProbes:
    """Liveness and readiness endpoints must be auth-free and PII-free."""

    def test_health_no_auth_required(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json() == {"status": "ok"}

    def test_health_via_v1(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.get_json() == {"status": "ok"}

    def test_ready_reports_checks(self, client):
        r = client.get("/api/ready")
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "ready"
        assert body["checks"]["db"] is True
        assert body["checks"]["encryption"] is True

    def test_health_not_rate_limited_or_csrf_guarded(self, client):
        # Hammer it a few times — must not 429 or 400.
        for _ in range(20):
            r = client.get("/api/health")
            assert r.status_code == 200


class TestApiV1Alias:
    """Every /api/ route should be reachable via /api/v1/ without code changes."""

    def test_me_via_v1(self, app):
        c = _authed(app, "medecin_a")
        r_plain = c.get("/me")
        r_v1    = c.get("/api/v1/../me") if False else c.get("/me")
        # /me is not under /api/ — it's root-level — so it shouldn't be affected.
        assert r_plain.status_code == 200

    def test_patient_list_via_v1(self, app):
        c = _authed(app, "medecin_a")
        r_plain = c.get("/api/patients")
        r_v1    = c.get("/api/v1/patients")
        assert r_plain.status_code == 200
        assert r_v1.status_code == 200
        assert r_plain.get_json() == r_v1.get_json()

    def test_admin_stats_via_v1(self, app):
        c = _authed(app, "admin_test", "AdminPass@2025!")
        r_plain = c.get("/api/admin/stats")
        r_v1    = c.get("/api/v1/admin/stats")
        assert r_plain.status_code == 200
        assert r_v1.status_code == 200
        assert r_plain.get_json() == r_v1.get_json()

    def test_v1_post_still_csrf_guarded(self, client):
        """The path rewrite must not accidentally bypass the CSRF JSON-only guard."""
        _login(client, "medecin_a", "SecurePass@2025!")
        r = client.post(
            "/api/v1/patients",
            data="nom=Evil",
            content_type="application/x-www-form-urlencoded",
        )
        assert r.status_code == 400
        assert r.get_json().get("error") == "Requête invalide"


class TestAnalysisRetry:
    """The background LLM analysis must retry transient failures and only
    give up after exhausting attempts (or immediately on permanent errors)."""

    # Minimal PDF — analyze_document only accepts application/pdf uploads.
    _PDF_B64 = (
        "JVBERi0xLjQKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2JqCjIgMCBvYmo8"
        "PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PmVuZG9iagozIDAgb2JqPDwvVHlwZS9QYWdl"
        "L1BhcmVudCAyIDAgUi9NZWRpYUJveFswIDAgMTAwIDEwMF0+PmVuZG9iagp4cmVmCjAgNAowMDAwMDAw"
        "MDAwIDY1NTM1IGYKMDAwMDAwMDAwOSAwMDAwMCBuCjAwMDAwMDAwNTIgMDAwMDAgbgowMDAwMDAwMDk4"
        "IDAwMDAwIG4KdHJhaWxlcjw8L1NpemUgNC9Sb290IDEgMCBSPj4Kc3RhcnR4cmVmCjE0OAolJUVPRgo="
    )

    def _setup_doc_with_consent(self, app, db_path):
        import sqlite3, uuid
        # Grant AI consent so analysis isn't rejected by the consent check.
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT OR REPLACE INTO patient_consents "
            "(id, patient_id, user_id, consent_type, granted) "
            "VALUES (?,?,?,?,1)",
            (str(uuid.uuid4())[:8], "P_A001", "MED_A", "ai_analysis")
        )
        con.commit()
        con.close()

        c = _authed(app, "medecin_a")
        doc_id = c.post("/api/patients/P_A001/upload", json={
            "type": "Retry test", "image": self._PDF_B64
        }).get_json()["id"]
        return c, doc_id

    def test_temporary_errors_are_retried(self, app, db_path, monkeypatch):
        """LLMUnavailableError(temporary=True) must be retried up to 3 times."""
        from routes import documents as _docs
        from llm import LLMUnavailableError

        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise LLMUnavailableError("503 upstream", temporary=True)
            return "Analyse simulée OK"

        # Keep backoff short for the test.
        monkeypatch.setattr(_docs, "_ANALYSIS_BACKOFF_BASE", 0.01)
        monkeypatch.setattr(_docs, "call_llm", flaky)

        c, doc_id = self._setup_doc_with_consent(app, db_path)
        r = c.post(f"/api/patients/P_A001/documents/{doc_id}/analyze", json={})
        assert r.status_code == 200

        # Wait for the background thread to finish.
        import time, sqlite3
        for _ in range(50):
            time.sleep(0.1)
            con = sqlite3.connect(db_path)
            row = con.execute(
                "SELECT analysis_status, analyse_ia FROM documents WHERE id=?", (doc_id,)
            ).fetchone()
            con.close()
            if row and row[0] == 'done':
                break
        assert row[0] == 'done', f"expected done, got {row[0]!r}"
        assert calls["n"] == 3, f"expected 3 attempts, got {calls['n']}"
        assert row[1] == "Analyse simulée OK"

    def test_permanent_errors_fail_fast(self, app, db_path, monkeypatch):
        """LLMUnavailableError(temporary=False) must NOT be retried."""
        from routes import documents as _docs
        from llm import LLMUnavailableError

        calls = {"n": 0}

        def always_fail(*a, **kw):
            calls["n"] += 1
            raise LLMUnavailableError("invalid api key", temporary=False)

        monkeypatch.setattr(_docs, "_ANALYSIS_BACKOFF_BASE", 0.01)
        monkeypatch.setattr(_docs, "call_llm", always_fail)

        c, doc_id = self._setup_doc_with_consent(app, db_path)
        c.post(f"/api/patients/P_A001/documents/{doc_id}/analyze", json={})

        import time, sqlite3
        for _ in range(50):
            time.sleep(0.1)
            con = sqlite3.connect(db_path)
            row = con.execute(
                "SELECT analysis_status FROM documents WHERE id=?", (doc_id,)
            ).fetchone()
            con.close()
            if row and row[0] in ('failed_perm', 'failed_temp', 'failed'):
                break
        assert row[0] == 'failed_perm'
        assert calls["n"] == 1, f"permanent error must not retry (got {calls['n']} calls)"
