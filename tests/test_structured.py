"""Deterministic answers are built from records and cite only the selected patient's records."""
import pytest
from fastapi.testclient import TestClient

from conftest import PATIENTS


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    return TestClient(app)


QUESTIONS = ["What medications are recorded?", "How have the recorded vital signs changed?", "What are the latest laboratory results?",
             "Are there portal messages awaiting a reply?", "What follow-up is documented and is any of it still open?",
             "What imaging is available?", "What information cannot be established from the available records?"]


@pytest.mark.parametrize("pid", PATIENTS)
@pytest.mark.parametrize("q", QUESTIONS)
def test_structured_answers_are_cited_and_scoped(client, pid, q):
    r = client.post(f"/api/patients/{pid}/ask", json={"question": q}).json()
    assert r["mode"] in ("structured", "policy")
    sids = {s["sid"] for s in r["sources"]}
    for c in r["claims"]:
        if c["kind"] == "documented":
            assert c["citations"] and set(c["citations"]) <= sids
        else:
            assert c["citations"] == []
    bundle = client.get(f"/api/patients/{pid}").json()
    own = {e["encounter_id"] for e in bundle["encounters"]}
    assert all(s["encounter_id"] in own for s in r["sources"] if s["encounter_id"])


def test_medication_change_answer_is_exact(client):
    r = client.post("/api/patients/CN-P002/ask", json={"question": "What medications are recorded?"}).json()
    texts = " ".join(c["text"] for c in r["claims"])
    assert "Insulin glargine changed from 10 units to 14 units on 20 Jul 2026" in texts
    assert "Empagliflozin 10 mg" in texts


def test_lab_trend_answer_is_exact(client):
    r = client.post("/api/patients/CN-P010/ask", json={"question": "How has LDL cholesterol changed over time?"}).json()
    assert r["claims"][0]["text"].startswith("LDL cholesterol (calculated) (mg/dL): 186 (15 Jun) → 132 (27 Jul) → 94 (14 Sep)")


def test_awaiting_reply_is_reported_with_quote(client):
    r = client.post("/api/patients/CN-P003/ask", json={"question": "Are there portal messages awaiting a reply?"}).json()
    first = r["claims"][0]["text"]
    assert first.startswith("Awaiting reply") and "83.0 kg" in first and "No care-team reply is recorded" in first


def test_imaging_answer_never_interprets(client):
    for pid in ("CN-P001", "CN-P005", "CN-P006"):
        r = client.post(f"/api/patients/{pid}/ask", json={"question": "What does the chest x-ray show?"}).json()
        assert r["route"] == "policy_imaging"
        text = " ".join(c["text"] for c in r["claims"]).lower()
        for word in ("opacity", "consolidation", "effusion", "fracture", "normal study", "infiltrate"):
            assert word not in text


def test_gaps_lists_scanned_documents(client):
    r = client.post("/api/patients/CN-P009/ask", json={"question": "What information cannot be established from the available records?"}).json()
    assert any("OCR was not performed" in c["text"] for c in r["claims"])
