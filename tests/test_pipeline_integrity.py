"""Data-integrity tests over the v5 pipeline output (same code path as the Databricks notebook)."""
import re

from conftest import PATIENTS


def test_all_integrity_checks_pass(processed):
    failing = [c for c in processed["integrity_checks"] if c["status"] != "pass"]
    assert not failing, failing
    assert len(processed["integrity_checks"]) >= 13


def test_misfiled_pdf_is_quarantined_and_absent(processed):
    q = processed["document_quarantine"]
    assert [x["document_id"] for x in q] == ["CN-D008-3"]
    assert "CN-P007" in q[0]["content_patient_ids"] and q[0]["indexed_patient_id"] == "CN-P008"
    assert all(d["document_id"] != "CN-D008-3" for d in processed["documents"])
    assert all(p["document_id"] != "CN-D008-3" for p in processed["document_pages"])
    assert all(c.get("document_id") != "CN-D008-3" for c in processed["knowledge_chunks"])


def test_scanned_pdfs_have_no_text_and_no_chunks(processed):
    scanned = [d for d in processed["documents"] if not d["has_text_layer"]]
    assert {d["document_id"] for d in scanned} == {"CN-D003-2", "CN-D009-1"}
    assert all(d["extraction_status"] == "no_text_layer" and d["identity_status"] == "unverified_no_text_layer" for d in scanned)
    ids = {d["document_id"] for d in scanned}
    assert not [c for c in processed["knowledge_chunks"] if c.get("document_id") in ids]


def test_every_text_page_prints_its_own_patient(processed):
    for p in processed["document_pages"]:
        if p["has_text_layer"]:
            assert set(re.findall(r"Patient ID:\s*(CN-P\d{3})", p["page_text"])) == {p["patient_id"]}, p["page_id"]


def test_pdf_chunks_carry_page_numbers(processed):
    pdf_chunks = [c for c in processed["knowledge_chunks"] if c["source_type"] == "pdf_document"]
    assert pdf_chunks and all(isinstance(c["page_number"], int) and c["page_number"] >= 1 for c in pdf_chunks)
    pages = {(p["document_id"], p["page_number"]) for p in processed["document_pages"]}
    assert all((c["document_id"], c["page_number"]) in pages for c in pdf_chunks)


def test_chunks_never_mention_other_patients(processed):
    for c in processed["knowledge_chunks"]:
        assert set(re.findall(r"CN-P\d{3}", c["chunk_text"])) <= {c["patient_id"]}, c["chunk_id"]


def test_every_patient_has_rich_multimodal_record(processed):
    for pid in PATIENTS:
        own = lambda t: [r for r in processed[t] if r["patient_id"] == pid]  # noqa: E731
        assert len(own("encounters")) >= 2
        assert len(own("observations")) >= 10
        assert own("medication_requests") and own("clinical_notes") and own("portal_threads") and own("documents")


def test_unanswered_messages_exist_and_are_consistent(processed):
    msgs = {}
    for m in processed["portal_messages"]:
        msgs.setdefault(m["thread_id"], []).append(m)
    awaiting = [t for t in processed["portal_threads"] if t["status"] == "awaiting_reply"]
    assert len(awaiting) >= 8
    for t in awaiting:
        last = sorted(msgs[t["thread_id"]], key=lambda m: m["sent_at"])[-1]
        assert last["sender_role"] == "patient"


def test_dicom_headers_verified_and_synthetic(processed):
    assert all(s["dicom_header_verified"] and s["stored_modality"] == "OT" and s["image_content"] == "synthetic_test_pattern"
               for s in processed["imaging_studies"])
    for r in processed["imaging_reports"]:
        assert "NOT A RADIOLOGY INTERPRETATION" in r["report_text"] and "not interpreted" in r["report_text"]


def test_blood_pressure_has_systolic_and_diastolic_pairs(processed):
    panels = {}
    for o in processed["observations"]:
        if o["panel_id"]:
            panels.setdefault(o["panel_id"], set()).add(o["measure_key"])
    assert panels and all(v == {"sbp", "dbp"} for v in panels.values())
