"""Patient isolation across the API, file access and the assistant."""
import pytest
from fastapi.testclient import TestClient

from conftest import PATIENTS


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    return TestClient(app)


@pytest.mark.parametrize("pid", PATIENTS)
def test_bundle_contains_only_requested_patient(client, pid):
    b = client.get(f"/api/patients/{pid}").json()
    for key in ["encounters", "conditions", "observations", "medications", "notes", "follow_ups", "threads", "imaging", "documents"]:
        assert all(r.get("patient_id", pid) == pid for r in b[key]), key
    for t in b["threads"]:
        assert all(m["patient_id"] == pid for m in t["messages"])
    for item in b["brief"]["items"]:
        for ref in item["refs"]:
            assert ref["id"].startswith(("CN-E" + pid[-3:], "CN-D" + pid[-3:], "CN-T" + pid[-3:], "CN-M" + pid[-3:],
                                         "CN-O" + pid[-3:], "CN-N" + pid[-3:], "CN-F" + pid[-3:]))


def test_cross_patient_document_and_image_access_is_denied(client):
    assert client.get("/api/patients/CN-P001/documents/CN-D003-1/file").status_code == 404
    assert client.get("/api/patients/CN-P001/documents/CN-D003-1/pages").status_code == 404
    assert client.get("/api/patients/CN-P002/imaging/CN-IMG003-1/image.png").status_code == 404
    assert client.get("/api/patients/CN-P002/imaging/CN-IMG003-1/metadata").status_code == 404
    assert client.get("/api/patients/CN-P003/documents/CN-D003-1/file").status_code == 200


def test_quarantined_document_never_served(client):
    for pid in ("CN-P007", "CN-P008"):
        assert client.get(f"/api/patients/{pid}/documents/CN-D008-3/file").status_code == 404
        assert all(d["document_id"] != "CN-D008-3" for d in client.get(f"/api/patients/{pid}").json()["documents"])


@pytest.mark.parametrize("bad", ["CN-P1", "1 OR 1=1", "CN-P001;DROP", "../etc"])
def test_malformed_patient_ids_rejected(client, bad):
    assert client.get(f"/api/patients/{bad}").status_code in (400, 404)


@pytest.mark.parametrize("pid", PATIENTS)
def test_retrieval_candidates_are_patient_scoped(pid):
    from backend.assistant.service import retrieve
    from backend.clinical import patient_bundle
    ranked, info = retrieve(pid, "medication discharge follow-up imaging message laboratory", patient_bundle(pid), top_k=50)
    assert ranked and all(c["patient_id"] == pid for c in ranked)
    assert info["mode"] == "lexical"  # embeddings blocked in tests -> graceful lexical fallback


def test_scope_error_raised_on_foreign_row():
    from backend.datasource import LocalSource, ScopeError
    src = LocalSource()
    src._load("encounters")
    src._tables["encounters"] = src._tables["encounters"] + [dict(src._tables["encounters"][0], patient_id="CN-P002")]
    original = src._fetch
    src._fetch = lambda t, p, c: [dict(r, patient_id="CN-P002") for r in original(t, p, c)][:1] if t == "encounters" else original(t, p, c)
    with pytest.raises(ScopeError):
        src.patient_rows("encounters", "CN-P001")


@pytest.mark.parametrize("q", ["What did CN-P002 have?", "Compare this patient with other patients", "List all patients with heart failure"])
def test_assistant_refuses_cross_patient_questions(client, q):
    r = client.post("/api/patients/CN-P001/ask", json={"question": q}).json()
    assert r["route"] == "policy_scope" and r["sources"] == [] and r["claims"] == []
