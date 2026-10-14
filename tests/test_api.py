"""API contract and read-model correctness."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    return TestClient(app)


def test_meta_and_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
    m = client.get("/api/meta").json()
    assert m["synthetic"] is True and m["dataset"]["dataset_version"] == "v5.0.0"


def test_worklist_flags(client):
    rows = {r["patient_id"]: r for r in client.get("/api/patients").json()}
    assert len(rows) == 10
    assert rows["CN-P006"]["awaiting_reply"] == 2 and rows["CN-P006"]["routed_pending"] == 1
    assert rows["CN-P009"]["overdue_follow_ups"] == 1
    assert rows["CN-P003"]["recent_acute_class"] == "IMP"


def test_brief_surfaces_key_items(client):
    items = client.get("/api/patients/CN-P003").json()["brief"]["items"]
    kinds = [i["kind"] for i in items]
    assert kinds[0] in ("awaiting_reply", "acute_care")
    assert {"awaiting_reply", "acute_care", "medication_changes", "abnormal_results", "unsearchable_documents"} <= set(kinds)
    acute = next(i for i in items if i["kind"] == "acute_care")
    assert any(r["type"] == "document" for r in acute["refs"])


def test_problem_list_collapses_superseded_codes(client):
    probs = client.get("/api/patients/CN-P003").json()["problems"]
    assert [p["code"] for p in probs] == ["I50.22"]


def test_pdf_and_pages(client):
    r = client.get("/api/patients/CN-P003/documents/CN-D003-1/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    pages = client.get("/api/patients/CN-P003/documents/CN-D003-1/pages").json()
    assert [p["page_number"] for p in pages] == list(range(1, len(pages) + 1))
    assert "Discharge Summary" in pages[0]["page_text"]


def test_dicom_render_and_metadata(client):
    meta = client.get("/api/patients/CN-P001/imaging/CN-IMG001-1/metadata").json()
    assert meta["conversion_type"] == "SYN" and meta["modality"] == "OT"
    png = client.get("/api/patients/CN-P001/imaging/CN-IMG001-1/image.png?wc=1500&ww=2000")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_operations(client):
    o = client.get("/api/operations").json()
    assert o["totals"]["encounters"] == 38 and o["documentation"]["quarantined"] == 1
    assert all(c["status"] == "pass" for c in o["quality"])


def test_question_validation(client):
    assert client.post("/api/patients/CN-P001/ask", json={"question": "a"}).status_code == 422
    assert client.post("/api/patients/CN-P001/ask", json={"question": "x" * 600}).status_code == 422


def test_suggestions_are_patient_specific(client):
    p9 = [s["q"] for s in client.get("/api/patients/CN-P009/suggestions").json()]
    p1 = [s["q"] for s in client.get("/api/patients/CN-P001/suggestions").json()]
    assert not any("imaging" in q.lower() for q in p9)
    assert any("hospital" in q.lower() for q in p1)


def test_no_patient_is_presented_as_currently_admitted(client):
    """Acute-care indicators are historical: every encounter is finished and the brief says 'discharged'."""
    for pid in [f"CN-P{i:03d}" for i in range(1, 11)]:
        b = client.get(f"/api/patients/{pid}").json()
        assert b["brief"]["active_encounter"] is None
        for item in b["brief"]["items"]:
            if item["kind"] == "acute_care":
                assert "(discharged)" in item["title"]
