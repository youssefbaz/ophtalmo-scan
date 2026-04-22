"""Tests for threaded conversations + audio messaging (routes/messages.py)."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _login(client, username, password="SecurePass@2025!"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.get_json().get("ok"), f"Login failed: {r.get_json()}"
    return client


def _authed(app, username, password="SecurePass@2025!"):
    c = app.test_client()
    return _login(c, username, password)


# Minimal valid WebM/EBML header — enough for _detect_audio_mime to accept.
WEBM_MAGIC = b"\x1aE\xdf\xa3"
FAKE_WEBM  = WEBM_MAGIC + b"\x00" * 256


# ─── Basic send / receive ────────────────────────────────────────────────────

class TestDoctorSendsText:
    def test_doctor_can_send_text_message(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/messages",
                   json={"contenu": "Bonjour Alice"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["message"]["contenu"] == "Bonjour Alice"
        assert data["message"]["sender_role"] == "medecin"
        assert data["message"]["has_audio"] is False
        assert data["message"]["conversation_id"].startswith("CONV")

    def test_empty_message_rejected(self, app):
        c = _authed(app, "medecin_a")
        r = c.post("/api/patients/P_A001/messages", json={"contenu": "   "})
        assert r.status_code == 400

    def test_other_doctor_cannot_send(self, app):
        c = _authed(app, "medecin_b")
        r = c.post("/api/patients/P_A001/messages",
                   json={"contenu": "Intrusion"})
        assert r.status_code == 403


class TestPatientSendsText:
    def test_patient_can_reply_with_text(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/messages/patient",
                   json={"contenu": "Merci docteur"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["message"]["sender_role"] == "patient"
        assert data["message"]["medecin_id"] == "MED_A"

    def test_patient_cannot_post_for_another_patient(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_OTHER/messages/patient",
                   json={"contenu": "hack"})
        assert r.status_code == 403

    def test_patient_empty_message_rejected(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/messages/patient",
                   json={"contenu": ""})
        assert r.status_code == 400


# ─── Conversation threading ──────────────────────────────────────────────────

class TestConversationThreading:
    def test_patient_and_doctor_share_same_open_thread(self, app):
        doc = _authed(app, "medecin_a")
        pat = _authed(app, "patient_a")

        r1 = pat.post("/api/patients/P_A001/messages/patient",
                      json={"contenu": "Question 1", "new_conversation": True})
        cid1 = r1.get_json()["message"]["conversation_id"]

        r2 = doc.post("/api/patients/P_A001/messages",
                      json={"contenu": "Réponse 1"})
        cid2 = r2.get_json()["message"]["conversation_id"]

        assert cid1 == cid2, "Doctor reply should land in the same open thread"

        r3 = pat.post("/api/patients/P_A001/messages/patient",
                      json={"contenu": "Question 2"})
        assert r3.get_json()["message"]["conversation_id"] == cid1

    def test_new_conversation_flag_starts_fresh_thread(self, app):
        pat = _authed(app, "patient_a")
        r1 = pat.post("/api/patients/P_A001/messages/patient",
                      json={"contenu": "Premier", "new_conversation": True})
        r2 = pat.post("/api/patients/P_A001/messages/patient",
                      json={"contenu": "Second",  "new_conversation": True})
        assert r1.get_json()["message"]["conversation_id"] \
            != r2.get_json()["message"]["conversation_id"]

    def test_closing_conversation_blocks_appending_to_it(self, app):
        doc = _authed(app, "medecin_a")
        pat = _authed(app, "patient_a")

        r = pat.post("/api/patients/P_A001/messages/patient",
                     json={"contenu": "Ouverture", "new_conversation": True})
        cid = r.get_json()["message"]["conversation_id"]

        close = doc.post(f"/api/conversations/{cid}/close", json={})
        assert close.status_code == 200
        assert close.get_json()["status"] == "closed"

        # Patient sends again → should open a brand-new conversation
        r2 = pat.post("/api/patients/P_A001/messages/patient",
                      json={"contenu": "Nouvelle"})
        assert r2.get_json()["message"]["conversation_id"] != cid

    def test_patient_cannot_close_conversation(self, app):
        pat = _authed(app, "patient_a")
        r = pat.post("/api/patients/P_A001/messages/patient",
                     json={"contenu": "x", "new_conversation": True})
        cid = r.get_json()["message"]["conversation_id"]
        r2 = pat.post(f"/api/conversations/{cid}/close", json={})
        assert r2.status_code == 403


# ─── Listing endpoints ───────────────────────────────────────────────────────

class TestConversationListing:
    def test_list_conversations_returns_expected_shape(self, app):
        pat = _authed(app, "patient_a")
        pat.post("/api/patients/P_A001/messages/patient",
                 json={"contenu": "Hello", "new_conversation": True})

        r = pat.get("/api/patients/P_A001/conversations")
        assert r.status_code == 200
        convs = r.get_json()
        assert isinstance(convs, list) and len(convs) >= 1
        c = convs[0]
        for k in ("id", "status", "patient_id", "medecin_id",
                  "unread", "last_preview", "medecin_nom"):
            assert k in c

    def test_other_doctor_cannot_list_conversations(self, app):
        _authed(app, "patient_a").post(
            "/api/patients/P_A001/messages/patient",
            json={"contenu": "ping", "new_conversation": True})
        doc_b = _authed(app, "medecin_b")
        r = doc_b.get("/api/patients/P_A001/conversations")
        assert r.status_code == 403

    def test_list_messages_marks_other_party_read(self, app):
        doc = _authed(app, "medecin_a")
        pat = _authed(app, "patient_a")

        r = doc.post("/api/patients/P_A001/messages",
                     json={"contenu": "Lis-moi"})
        cid = r.get_json()["message"]["conversation_id"]

        # Before fetch: unread=1 for the patient
        pre = pat.get("/api/patients/P_A001/conversations").get_json()
        conv_pre = next(c for c in pre if c["id"] == cid)
        assert conv_pre["unread"] == 1

        fetched = pat.get(f"/api/conversations/{cid}/messages")
        assert fetched.status_code == 200
        assert len(fetched.get_json()["messages"]) >= 1

        # After fetch: unread goes to 0
        post = pat.get("/api/patients/P_A001/conversations").get_json()
        conv_post = next(c for c in post if c["id"] == cid)
        assert conv_post["unread"] == 0


# ─── Audio upload + streaming ────────────────────────────────────────────────

class TestAudioMessaging:
    def test_patient_can_upload_audio_message(self, app):
        c = _authed(app, "patient_a")
        data = {
            "contenu": "",
            "audio_duration_sec": "3",
            "new_conversation": "1",
        }
        data["audio"] = (io.BytesIO(FAKE_WEBM), "voice.webm")
        r = c.post("/api/patients/P_A001/messages/patient",
                   data=data, content_type="multipart/form-data",
                   headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 200
        msg = r.get_json()["message"]
        assert msg["has_audio"] is True
        assert msg["audio_duration_sec"] == 3

    def test_audio_stream_returned_to_authorized_viewer(self, app):
        pat = _authed(app, "patient_a")
        data = {
            "contenu": "",
            "audio_duration_sec": "2",
            "new_conversation": "1",
            "audio": (io.BytesIO(FAKE_WEBM), "voice.webm"),
        }
        r = pat.post("/api/patients/P_A001/messages/patient",
                     data=data, content_type="multipart/form-data",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        mid = r.get_json()["message"]["id"]

        # Patient can fetch their own audio
        r1 = pat.get(f"/api/messages/{mid}/audio")
        assert r1.status_code == 200
        assert r1.mimetype.startswith("audio/")
        assert r1.data[:4] == WEBM_MAGIC  # bytes round-trip through encrypt/decrypt

        # Owning doctor can fetch too
        doc = _authed(app, "medecin_a")
        r2 = doc.get(f"/api/messages/{mid}/audio")
        assert r2.status_code == 200

        # Other doctor blocked
        doc_b = _authed(app, "medecin_b")
        r3 = doc_b.get(f"/api/messages/{mid}/audio")
        assert r3.status_code == 403

    def test_audio_stream_requires_auth(self, app):
        pat = _authed(app, "patient_a")
        data = {
            "contenu": "",
            "audio_duration_sec": "1",
            "new_conversation": "1",
            "audio": (io.BytesIO(FAKE_WEBM), "voice.webm"),
        }
        r = pat.post("/api/patients/P_A001/messages/patient",
                     data=data, content_type="multipart/form-data",
                   headers={"X-Requested-With": "XMLHttpRequest"})
        mid = r.get_json()["message"]["id"]

        anon = app.test_client()
        r_anon = anon.get(f"/api/messages/{mid}/audio")
        assert r_anon.status_code == 401

    def test_invalid_audio_magic_rejected(self, app):
        c = _authed(app, "patient_a")
        bad = {
            "contenu": "",
            "audio_duration_sec": "1",
            "new_conversation": "1",
            "audio": (io.BytesIO(b"NOTAUDIO" * 50), "fake.webm"),
        }
        r = c.post("/api/patients/P_A001/messages/patient",
                   data=bad, content_type="multipart/form-data",
                   headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 400
        assert "Format audio" in r.get_json()["error"]

    def test_audio_size_cap_enforced(self, app):
        c = _authed(app, "patient_a")
        huge = WEBM_MAGIC + b"\x00" * (9 * 1024 * 1024)  # > 8 MB cap
        data = {
            "contenu": "",
            "audio_duration_sec": "10",
            "new_conversation": "1",
            "audio": (io.BytesIO(huge), "big.webm"),
        }
        r = c.post("/api/patients/P_A001/messages/patient",
                   data=data, content_type="multipart/form-data",
                   headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 413
