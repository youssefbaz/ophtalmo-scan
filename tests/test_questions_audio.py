"""Tests for audio support on patient questions / doctor responses."""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


WEBM_MAGIC = b"\x1aE\xdf\xa3"
FAKE_WEBM  = WEBM_MAGIC + b"\x00" * 128

XHR = {"X-Requested-With": "XMLHttpRequest"}


def _login(client, username, password="SecurePass@2025!"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.get_json().get("ok")
    return client


def _authed(app, username, password="SecurePass@2025!"):
    return _login(app.test_client(), username, password)


def _post_audio_question(client, pid, text="", audio=FAKE_WEBM, duration=5):
    data = {"question": text, "audio_duration_sec": str(duration),
            "audio": (io.BytesIO(audio), "q.webm")}
    return client.post(f"/api/patients/{pid}/questions",
                       data=data, content_type="multipart/form-data", headers=XHR)


class TestPatientQuestionAudio:
    def test_audio_only_question_accepted(self, app):
        c = _authed(app, "patient_a")
        r = _post_audio_question(c, "P_A001", text="", duration=3)
        assert r.status_code == 200
        q = r.get_json()["question"]
        assert q["has_question_audio"] is True
        assert q["question_audio_duration"] == 3

    def test_text_and_audio_combined(self, app):
        c = _authed(app, "patient_a")
        r = _post_audio_question(c, "P_A001", text="Combinée", duration=2)
        assert r.status_code == 200
        q = r.get_json()["question"]
        assert q["question"] == "Combinée"
        assert q["has_question_audio"] is True

    def test_empty_both_rejected(self, app):
        c = _authed(app, "patient_a")
        r = c.post("/api/patients/P_A001/questions",
                   json={"question": "  "})
        assert r.status_code == 400

    def test_audio_endpoint_streams_back_original_bytes(self, app):
        c = _authed(app, "patient_a")
        r = _post_audio_question(c, "P_A001", text="", duration=1)
        qid = r.get_json()["question"]["id"]
        stream = c.get(f"/api/questions/{qid}/audio/question")
        assert stream.status_code == 200
        assert stream.mimetype.startswith("audio/")
        assert stream.data[:4] == WEBM_MAGIC

    def test_other_doctor_cannot_stream_audio(self, app):
        pat = _authed(app, "patient_a")
        r = _post_audio_question(pat, "P_A001", text="", duration=1)
        qid = r.get_json()["question"]["id"]
        doc_b = _authed(app, "medecin_b")
        r2 = doc_b.get(f"/api/questions/{qid}/audio/question")
        assert r2.status_code == 403

    def test_patient_can_delete_own_pending_question(self, app):
        c = _authed(app, "patient_a")
        r = _post_audio_question(c, "P_A001", text="à supprimer", duration=1)
        qid = r.get_json()["question"]["id"]
        r2 = c.delete(f"/api/patients/P_A001/questions/{qid}", headers=XHR)
        assert r2.status_code == 200


class TestDoctorResponseAudio:
    def test_doctor_can_reply_with_audio(self, app):
        pat = _authed(app, "patient_a")
        r = pat.post("/api/patients/P_A001/questions",
                     json={"question": "Ma question texte"})
        qid = r.get_json()["question"]["id"]

        doc = _authed(app, "medecin_a")
        data = {"reponse": "Texte + audio", "audio_duration_sec": "4",
                "audio": (io.BytesIO(FAKE_WEBM), "r.webm")}
        r2 = doc.post(f"/api/patients/P_A001/questions/{qid}/repondre",
                      data=data, content_type="multipart/form-data", headers=XHR)
        assert r2.status_code == 200
        body = r2.get_json()
        assert body["ok"] is True
        assert body["has_reponse_audio"] is True
        assert body["reponse_audio_duration"] == 4

        # Stream the response audio back
        stream = doc.get(f"/api/questions/{qid}/audio/reponse")
        assert stream.status_code == 200
        assert stream.data[:4] == WEBM_MAGIC

        # Patient can stream it too
        stream_p = pat.get(f"/api/questions/{qid}/audio/reponse")
        assert stream_p.status_code == 200

    def test_invalid_audio_rejected_on_question(self, app):
        c = _authed(app, "patient_a")
        data = {"question": "", "audio_duration_sec": "1",
                "audio": (io.BytesIO(b"JUNKDATA" * 10), "bad.webm")}
        r = c.post("/api/patients/P_A001/questions",
                   data=data, content_type="multipart/form-data", headers=XHR)
        assert r.status_code == 400
        assert "Format audio" in r.get_json()["error"]
