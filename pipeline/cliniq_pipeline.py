"""ClinIQ Nexus v5 ingestion library.

Pure-Python functions shared by the Databricks notebook (notebooks/v5_ingest.py) and the
local build (python pipeline/cliniq_pipeline.py). Given the raw synthetic drop (FHIR-style
NDJSON, PDFs, DICOM) it produces the curated tables, verified document pages, retrieval
chunks, optional embeddings and integrity-check results.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone

PIPELINE_VERSION = "2026.10.1"
MIN_TEXT_CHARS = 40                      # below this a page is treated as having no text layer
CHUNK_CHARS = 900
EMBED_MODEL = "databricks-gte-large-en"
ID_PATTERN = re.compile(r"Patient ID:\s*(CN-P\d{3})")
ENC_PATTERN = re.compile(r"Encounter:\s*(CN-E\d{3}-\d{2})")
ANY_PATIENT = re.compile(r"CN-P\d{3}")
BOILERPLATE = [
    re.compile(r"^Nexus General Hospital \(fictional\)$"),
    re.compile(r"^SYNTHETIC DEMONSTRATION DOCUMENT — NOT FOR CLINICAL USE$"),
    re.compile(r"^Synthetic Patient \d{3}\s+\|\s+Patient ID:.*$"),
    re.compile(r"^Document CN-D\d{3}-\d+\s+\|.*$"),
    re.compile(r"^Page \d+ of \d+$"),
]

RAW_TABLES = ["patients", "encounters", "conditions", "observations", "medication_requests", "clinical_notes",
              "follow_up_items", "portal_threads", "portal_messages", "imaging_studies", "imaging_reports",
              "document_index"]

# Unity Catalog DDL for every curated table (also serves as data dictionary).
TABLE_SCHEMAS = {
    "patients": "patient_id STRING, display_name STRING, mrn STRING, sex STRING, birth_date STRING, age_years INT, primary_clinician STRING, care_program STRING, program_summary STRING, is_synthetic BOOLEAN",
    "encounters": "encounter_id STRING, patient_id STRING, status STRING, class_code STRING, class_display STRING, encounter_type STRING, service STRING, attending STRING, location STRING, reason STRING, disposition STRING, start_at STRING, end_at STRING, duration_hours DOUBLE, is_synthetic BOOLEAN",
    "conditions": "condition_id STRING, patient_id STRING, encounter_id STRING, code_system STRING, code STRING, display STRING, clinical_status STRING, category STRING, recorded_at STRING, is_synthetic BOOLEAN",
    "observations": "observation_id STRING, patient_id STRING, encounter_id STRING, category STRING, code_system STRING, code STRING, measure_key STRING, name STRING, value DOUBLE, unit STRING, display_unit STRING, ref_low DOUBLE, ref_high DOUBLE, interpretation STRING, panel_id STRING, effective_at STRING, is_synthetic BOOLEAN",
    "medication_requests": "medication_request_id STRING, patient_id STRING, encounter_id STRING, medication STRING, dose STRING, route STRING, frequency STRING, category STRING, action STRING, status STRING, authored_on STRING, end_date STRING, prior_request_id STRING, reason STRING, stop_reason STRING, prescriber STRING, is_synthetic BOOLEAN",
    "clinical_notes": "note_id STRING, patient_id STRING, encounter_id STRING, note_type STRING, author STRING, authored_at STRING, title STRING, note_text STRING, is_synthetic BOOLEAN",
    "follow_up_items": "follow_up_id STRING, patient_id STRING, encounter_id STRING, description STRING, due_date STRING, status STRING, resolved_encounter_id STRING, source_note_id STRING, is_synthetic BOOLEAN",
    "portal_threads": "thread_id STRING, patient_id STRING, encounter_id STRING, subject STRING, category STRING, status STRING, routed_to STRING, opened_at STRING, last_message_at STRING, last_sender_role STRING, message_count INT, first_response_minutes INT, is_synthetic BOOLEAN",
    "portal_messages": "message_id STRING, thread_id STRING, patient_id STRING, encounter_id STRING, channel STRING, sender_role STRING, sender_name STRING, sent_at STRING, subject STRING, message_body STRING, is_routing_acknowledgment BOOLEAN, is_synthetic BOOLEAN",
    "imaging_studies": "study_id STRING, patient_id STRING, encounter_id STRING, accession_number STRING, ordered_procedure STRING, indication STRING, stored_modality STRING, sop_class STRING, image_content STRING, study_at STRING, dicom_path STRING, report_id STRING, ordering_clinician STRING, study_uid STRING, sop_uid STRING, rows INT, columns INT, dicom_header_verified BOOLEAN, is_synthetic BOOLEAN",
    "imaging_reports": "report_id STRING, study_id STRING, patient_id STRING, encounter_id STRING, status STRING, report_text STRING, authored_at STRING, is_synthetic BOOLEAN",
    "documents": "document_id STRING, patient_id STRING, encounter_id STRING, doc_kind STRING, doc_type STRING, title STRING, author STRING, authored_at STRING, file_name STRING, file_path STRING, received_via STRING, page_count INT, file_bytes BIGINT, sha256 STRING, has_text_layer BOOLEAN, extraction_status STRING, identity_status STRING, identity_detail STRING, is_synthetic BOOLEAN",
    "document_pages": "page_id STRING, document_id STRING, patient_id STRING, encounter_id STRING, page_number INT, page_text STRING, char_count INT, has_text_layer BOOLEAN, is_synthetic BOOLEAN",
    "document_quarantine": "document_id STRING, indexed_patient_id STRING, indexed_encounter_id STRING, content_patient_ids STRING, content_encounter_ids STRING, reason STRING, file_path STRING, detected_at STRING, is_synthetic BOOLEAN",
    "knowledge_chunks": "chunk_id STRING, patient_id STRING, encounter_id STRING, source_type STRING, source_id STRING, document_id STRING, page_number INT, section STRING, label STRING, source_date STRING, chunk_text STRING, char_count INT, content_sha256 STRING, is_synthetic BOOLEAN",
    "chunk_embeddings": "chunk_id STRING, patient_id STRING, model STRING, dims INT, embedding ARRAY<FLOAT>, is_synthetic BOOLEAN",
    "integrity_checks": "check_id STRING, check_name STRING, category STRING, description STRING, status STRING, checked_count INT, failing_count INT, detail STRING, checked_at STRING",
    "dataset_manifest": "key STRING, value STRING",
}


# --------------------------------------------------------------------------- utilities

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_date(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.strftime("%d %b %Y").lstrip("0")


def load_raw(raw_dir: str) -> dict[str, list[dict]]:
    data = {}
    for name in RAW_TABLES:
        with open(os.path.join(raw_dir, "fhir", f"{name}.ndjson")) as f:
            data[name] = [json.loads(line) for line in f if line.strip()]
    return data


# --------------------------------------------------------------------------- PDF handling

def extract_pdf(data: bytes) -> list[dict]:
    """Return per-page text using the PDF text layer only (no OCR is attempted)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append({"page_number": i, "text": text, "char_count": len(text), "has_text_layer": len(text) >= MIN_TEXT_CHARS})
    return pages


def strip_boilerplate(text: str) -> str:
    keep = [ln for ln in text.splitlines() if not any(p.match(ln.strip()) for p in BOILERPLATE)]
    return "\n".join(keep).strip()


def verify_identity(index_row: dict, pages: list[dict], encounters: dict[str, dict]) -> dict:
    """Compare identifiers printed on every text page with the document index entry."""
    enc = encounters.get(index_row["encounter_id"])
    if enc is None or enc["patient_id"] != index_row["patient_id"]:
        return {"status": "quarantined", "reason": "Indexed encounter does not belong to indexed patient",
                "patients": [], "encounters": []}
    text_pages = [p for p in pages if p["has_text_layer"]]
    if not text_pages:
        return {"status": "unverified_no_text_layer",
                "reason": "No extractable text layer (scanned image). OCR not performed; association taken from document index only.",
                "patients": [], "encounters": []}
    found_p, found_e, missing = set(), set(), []
    for p in text_pages:
        ids = set(ID_PATTERN.findall(p["text"]))
        encs = set(ENC_PATTERN.findall(p["text"]))
        if not ids:
            missing.append(p["page_number"])
        found_p |= ids
        found_e |= encs
    if found_p and found_p != {index_row["patient_id"]}:
        return {"status": "quarantined", "reason": f"Patient identifier mismatch: index {index_row['patient_id']}, content {sorted(found_p)}",
                "patients": sorted(found_p), "encounters": sorted(found_e)}
    if found_e and found_e != {index_row["encounter_id"]}:
        return {"status": "quarantined", "reason": f"Encounter identifier mismatch: index {index_row['encounter_id']}, content {sorted(found_e)}",
                "patients": sorted(found_p), "encounters": sorted(found_e)}
    if missing:
        return {"status": "quarantined", "reason": f"Patient identifier missing on page(s) {missing}",
                "patients": sorted(found_p), "encounters": sorted(found_e)}
    return {"status": "verified", "reason": "Patient and encounter identifiers on every page match the document index.",
            "patients": sorted(found_p), "encounters": sorted(found_e)}


# --------------------------------------------------------------------------- chunking

def split_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n(?=[A-Z][A-Za-z /()&-]{2,40}\n)|\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > limit:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
        while len(cur) > limit * 1.4:
            cut = cur.rfind(". ", 0, limit)
            cut = cut + 1 if cut > limit // 2 else limit
            chunks.append(cur[:cut].strip())
            cur = cur[cut:].strip()
    if cur:
        chunks.append(cur)
    return chunks


def note_sections(text: str) -> list[tuple[str, str]]:
    blocks = [b for b in text.split("\n\n") if b.strip()]
    out = []
    for b in blocks[1:]:
        lines = b.splitlines()
        if lines[0].isupper() and len(lines) > 1:
            out.append((lines[0].title(), "\n".join(lines[1:])))
    return out


def chunk(rows: list[dict], **fields) -> None:
    text = fields["chunk_text"]
    rows.append({"char_count": len(text), "content_sha256": sha256_bytes(text.encode()), "is_synthetic": True, **fields})


def build_chunks(data: dict, documents: list[dict], pages: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for n in data["clinical_notes"]:
        sections = note_sections(n["note_text"])
        groups, cur, cur_names = [], "", []
        for name, body in sections:
            piece = f"{name}: {body}"
            if cur and len(cur) + len(piece) > CHUNK_CHARS:
                groups.append((cur_names, cur))
                cur, cur_names = piece, [name]
            else:
                cur = f"{cur}\n{piece}" if cur else piece
                cur_names.append(name)
        if cur:
            groups.append((cur_names, cur))
        for i, (names, body) in enumerate(groups, start=1):
            chunk(rows, chunk_id=f"{n['note_id']}-c{i}", patient_id=n["patient_id"], encounter_id=n["encounter_id"],
                  source_type="clinical_note", source_id=n["note_id"], document_id=None, page_number=None,
                  section=", ".join(names), label=f"{n['note_type']} · {short_date(n['authored_at'])}",
                  source_date=n["authored_at"], chunk_text=f"{n['note_type']} ({short_date(n['authored_at'])}).\n{body}")
    docs = {d["document_id"]: d for d in documents}
    for p in pages:
        d = docs[p["document_id"]]
        if not p["has_text_layer"]:
            continue
        body = strip_boilerplate(p["page_text"])
        for i, part in enumerate(split_text(body), start=1):
            chunk(rows, chunk_id=f"{p['page_id']}-c{i}", patient_id=d["patient_id"], encounter_id=d["encounter_id"],
                  source_type="pdf_document", source_id=d["document_id"], document_id=d["document_id"],
                  page_number=p["page_number"], section=None,
                  label=f"{d['title']} · p.{p['page_number']} · {short_date(d['authored_at'])}",
                  source_date=d["authored_at"], chunk_text=f"{d['title']} ({short_date(d['authored_at'])}), page {p['page_number']}.\n{part}")
    for m in data["portal_messages"]:
        who = "Patient" if m["sender_role"] == "patient" else m["sender_name"]
        chunk(rows, chunk_id=f"{m['message_id']}-c1", patient_id=m["patient_id"], encounter_id=m["encounter_id"],
              source_type="portal_message", source_id=m["message_id"], document_id=None, page_number=None,
              section=m["thread_id"], label=f"Portal message · {who} · {short_date(m['sent_at'])}",
              source_date=m["sent_at"],
              chunk_text=f"Patient portal message ({short_date(m['sent_at'])}). Subject: {m['subject']}. From: {who}.\n{m['message_body']}")
    for r in data["imaging_reports"]:
        chunk(rows, chunk_id=f"{r['report_id']}-c1", patient_id=r["patient_id"], encounter_id=r["encounter_id"],
              source_type="imaging_report", source_id=r["report_id"], document_id=None, page_number=None,
              section=r["study_id"], label=f"Imaging report (demonstration) · {short_date(r['authored_at'])}",
              source_date=r["authored_at"], chunk_text=r["report_text"])
    return rows


# --------------------------------------------------------------------------- embeddings

def embed_texts(texts: list[str], client=None, batch: int = 8, pause_s: float = 1.2) -> list[list[float]]:
    """Embed with the Databricks pay-per-token endpoint (gte-large-en, 1024 dims).

    Free Edition enforces a low workspace QPS limit on pay-per-token endpoints, so requests
    are sent in small paced batches (16 inputs per request is rejected with HTTP 429).
    """
    import time

    if client is None:
        from databricks.sdk import WorkspaceClient
        client = WorkspaceClient()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch):
        resp = client.api_client.do("POST", f"/serving-endpoints/{EMBED_MODEL}/invocations", body={"input": texts[i:i + batch]})
        vectors.extend([list(map(float, d["embedding"])) for d in resp["data"]])
        time.sleep(pause_s)
    return vectors


# --------------------------------------------------------------------------- integrity checks

def run_checks(t: dict[str, list[dict]], expected_quarantine: int | None = None) -> list[dict]:
    checks: list[dict] = []
    stamp = now_iso()

    def add(cid, name, category, description, checked, failing, detail=""):
        checks.append({"check_id": cid, "check_name": name, "category": category, "description": description,
                       "status": "pass" if failing == 0 else "fail", "checked_count": checked,
                       "failing_count": failing, "detail": detail, "checked_at": stamp})

    encs = {e["encounter_id"]: e for e in t["encounters"]}
    all_rows = [(name, r) for name, rows in t.items() if name not in ("integrity_checks", "dataset_manifest") for r in rows]
    bad = [n for n, r in all_rows if r.get("is_synthetic") is not True]
    add("DQ-01", "Synthetic flag on every record", "Compliance", "Every curated row carries is_synthetic = true.",
        len(all_rows), len(bad), ", ".join(sorted(set(bad))))

    linked = ["conditions", "observations", "medication_requests", "clinical_notes", "follow_up_items", "portal_threads",
              "portal_messages", "imaging_studies", "imaging_reports", "documents", "document_pages", "knowledge_chunks"]
    rows = [(n, r) for n in linked for r in t[n]]
    orphans = [f"{n}:{r.get('encounter_id')}" for n, r in rows
               if r.get("encounter_id") not in encs or encs[r["encounter_id"]]["patient_id"] != r["patient_id"]]
    add("DQ-02", "Patient–encounter linkage", "Referential integrity",
        "Each record's encounter exists and belongs to the same patient.", len(rows), len(orphans), "; ".join(orphans[:5]))

    leaks = [c["chunk_id"] for c in t["knowledge_chunks"] if any(p != c["patient_id"] for p in ANY_PATIENT.findall(c["chunk_text"]))]
    add("DQ-03", "No cross-patient identifiers in retrieval text", "Patient isolation",
        "No knowledge chunk mentions another patient's identifier.", len(t["knowledge_chunks"]), len(leaks), ", ".join(leaks[:5]))

    q_ids = {q["document_id"] for q in t["document_quarantine"]}
    leaked_q = [c["chunk_id"] for c in t["knowledge_chunks"] if c.get("document_id") in q_ids]
    leaked_q += [d["document_id"] for d in t["documents"] if d["document_id"] in q_ids]
    add("DQ-04", "Quarantined PDFs excluded", "Patient isolation",
        "Documents whose printed identifiers disagree with the index are quarantined and absent from documents, pages and chunks.",
        len(q_ids), len(leaked_q), f"{len(q_ids)} document(s) quarantined: " + ", ".join(sorted(q_ids)))
    if expected_quarantine is not None:
        add("DQ-05", "Misfiled-document detection", "Patient isolation",
            "The seeded misfiled PDF is detected by page-level identity verification.",
            expected_quarantine, abs(expected_quarantine - len(q_ids)), "")

    verified = [d for d in t["documents"] if d["identity_status"] == "verified"]
    pages_ok = [p for p in t["document_pages"] if p["has_text_layer"]]
    mismatched = [p["page_id"] for p in pages_ok if set(ID_PATTERN.findall(p["page_text"])) != {p["patient_id"]}]
    add("DQ-06", "Page-level patient identity", "Document integrity",
        "Every extracted PDF page prints the patient identifier it is filed under.", len(pages_ok), len(mismatched), ", ".join(mismatched[:5]))

    scanned = [d for d in t["documents"] if not d["has_text_layer"]]
    scanned_chunks = [c for c in t["knowledge_chunks"] if c.get("document_id") in {d["document_id"] for d in scanned}]
    add("DQ-07", "Scanned PDFs flagged, not OCR'd", "Document integrity",
        "Image-only PDFs are labelled no_text_layer and contribute no retrieval text.", len(scanned), len(scanned_chunks),
        f"{len(scanned)} scanned document(s); {len(verified)} verified text documents")

    dicom_bad = [s["study_id"] for s in t["imaging_studies"] if not s.get("dicom_header_verified")]
    add("DQ-08", "DICOM header matches study record", "Imaging integrity",
        "DICOM PatientID, AccessionNumber and synthetic ConversionType agree with the imaging catalog.",
        len(t["imaging_studies"]), len(dicom_bad), ", ".join(dicom_bad))

    rpt = {r["study_id"]: r for r in t["imaging_reports"]}
    bad_rpt = [s["study_id"] for s in t["imaging_studies"]
               if s["report_id"] != rpt.get(s["study_id"], {}).get("report_id") or rpt[s["study_id"]]["patient_id"] != s["patient_id"]]
    add("DQ-09", "Study-to-report association", "Imaging integrity", "Each study links to exactly one report for the same patient.",
        len(t["imaging_studies"]), len(bad_rpt), ", ".join(bad_rpt))

    msgs: dict[str, list[dict]] = {}
    for m in t["portal_messages"]:
        msgs.setdefault(m["thread_id"], []).append(m)
    wrong = []
    for th in t["portal_threads"]:
        last = sorted(msgs[th["thread_id"]], key=lambda m: m["sent_at"])[-1]
        expect = "awaiting_reply" if last["sender_role"] == "patient" else ("routed" if last["is_routing_acknowledgment"] else "answered")
        if th["status"] != expect or any(m["patient_id"] != th["patient_id"] for m in msgs[th["thread_id"]]):
            wrong.append(th["thread_id"])
    add("DQ-10", "Portal thread status derivation", "Care coordination",
        "Thread status (awaiting reply / routed / answered) matches the last message in the thread.",
        len(t["portal_threads"]), len(wrong), ", ".join(wrong))

    meds = {m["medication_request_id"]: m for m in t["medication_requests"]}
    chain_bad = [m["medication_request_id"] for m in meds.values()
                 if m["prior_request_id"] and (m["prior_request_id"] not in meds or meds[m["prior_request_id"]]["patient_id"] != m["patient_id"])]
    add("DQ-11", "Medication change chains", "Medication integrity",
        "Every dose change references a prior order for the same patient.", len(meds), len(chain_bad), ", ".join(chain_bad))

    obs_by_enc: dict[str, list[dict]] = {}
    for o in t["observations"]:
        obs_by_enc.setdefault(o["encounter_id"], []).append(o)
    notes_bad = []
    for n in t["clinical_notes"]:
        for o in obs_by_enc.get(n["encounter_id"], []):
            v = o["value"]
            token = str(int(v)) if float(v).is_integer() else f"{v:g}"
            if token not in n["note_text"]:
                notes_bad.append(f"{n['note_id']}:{o['observation_id']}")
    add("DQ-12", "Note values match structured observations", "Clinical consistency",
        "Every observation recorded at an encounter appears with the same value in that encounter's note.",
        len(t["observations"]), len(notes_bad), ", ".join(notes_bad[:5]))

    fu_bad = []
    for f in t["follow_up_items"]:
        if f["resolved_encounter_id"]:
            r = encs.get(f["resolved_encounter_id"])
            if not r or r["patient_id"] != f["patient_id"] or r["start_at"] < encs[f["encounter_id"]]["start_at"]:
                fu_bad.append(f["follow_up_id"])
    add("DQ-13", "Follow-up resolution chronology", "Care coordination",
        "Completed follow-up items resolve to a later encounter of the same patient.",
        len(t["follow_up_items"]), len(fu_bad), ", ".join(fu_bad))

    if t.get("chunk_embeddings"):
        emb_ids = {e["chunk_id"]: e for e in t["chunk_embeddings"]}
        miss = [c["chunk_id"] for c in t["knowledge_chunks"]
                if c["chunk_id"] not in emb_ids or emb_ids[c["chunk_id"]]["patient_id"] != c["patient_id"]]
        add("DQ-14", "Embedding coverage", "Retrieval", "Every chunk has an embedding stored under the same patient.",
            len(t["knowledge_chunks"]), len(miss), ", ".join(miss[:5]))
    return checks


# --------------------------------------------------------------------------- orchestration

def verify_dicom(study: dict, data: bytes) -> bool:
    import pydicom

    ds = pydicom.dcmread(io.BytesIO(data))
    return (ds.PatientID == study["patient_id"] and ds.AccessionNumber == study["accession_number"]
            and ds.Modality == "OT" and getattr(ds, "ConversionType", "") == "SYN")


def process(raw_dir: str, read_bytes=None, embed: bool = False, embed_client=None, expected_quarantine: int | None = 1) -> dict:
    """Build every curated table. ``read_bytes(rel_path)`` reads a raw file (defaults to local disk)."""
    read_bytes = read_bytes or (lambda rel: open(os.path.join(raw_dir, rel), "rb").read())
    data = load_raw(raw_dir)
    encounters = {e["encounter_id"]: e for e in data["encounters"]}

    documents, pages, quarantine = [], [], []
    for d in data["document_index"]:
        blob = read_bytes(f"documents/{d['file_name']}")
        extracted = extract_pdf(blob)
        ident = verify_identity(d, extracted, encounters)
        has_text = any(p["has_text_layer"] for p in extracted)
        if ident["status"] == "quarantined":
            quarantine.append({"document_id": d["document_id"], "indexed_patient_id": d["patient_id"],
                               "indexed_encounter_id": d["encounter_id"], "content_patient_ids": ",".join(ident["patients"]),
                               "content_encounter_ids": ",".join(ident["encounters"]), "reason": ident["reason"],
                               "file_path": d["file_path"], "detected_at": now_iso(), "is_synthetic": True})
            continue
        row = {k: d[k] for k in ["document_id", "patient_id", "encounter_id", "doc_kind", "doc_type", "title", "author",
                                 "authored_at", "file_name", "file_path", "received_via"]}
        row.update(page_count=len(extracted), file_bytes=len(blob), sha256=sha256_bytes(blob), has_text_layer=has_text,
                   extraction_status="extracted" if has_text else "no_text_layer",
                   identity_status=ident["status"], identity_detail=ident["reason"], is_synthetic=True)
        documents.append(row)
        for p in extracted:
            pages.append({"page_id": f"{d['document_id']}-p{p['page_number']}", "document_id": d["document_id"],
                          "patient_id": d["patient_id"], "encounter_id": d["encounter_id"], "page_number": p["page_number"],
                          "page_text": p["text"], "char_count": p["char_count"], "has_text_layer": p["has_text_layer"],
                          "is_synthetic": True})

    for s in data["imaging_studies"]:
        s["dicom_header_verified"] = verify_dicom(s, read_bytes(f"dicom/{s['study_id']}.dcm"))

    tables = {k: v for k, v in data.items() if k != "document_index"}
    tables.update(documents=documents, document_pages=pages, document_quarantine=quarantine)
    tables["knowledge_chunks"] = build_chunks(data, documents, pages)
    tables["chunk_embeddings"] = []
    if embed:
        vecs = embed_texts([c["chunk_text"] for c in tables["knowledge_chunks"]], client=embed_client)
        tables["chunk_embeddings"] = [{"chunk_id": c["chunk_id"], "patient_id": c["patient_id"], "model": EMBED_MODEL,
                                       "dims": len(v), "embedding": v, "is_synthetic": True}
                                      for c, v in zip(tables["knowledge_chunks"], vecs)]
    tables["integrity_checks"] = run_checks(tables, expected_quarantine)
    manifest = json.loads(read_bytes("manifest.json"))
    tables["dataset_manifest"] = [
        {"key": "dataset_version", "value": manifest["dataset_version"]},
        {"key": "as_of", "value": manifest["as_of"]},
        {"key": "pipeline_version", "value": PIPELINE_VERSION},
        {"key": "processed_at", "value": now_iso()},
        {"key": "embedding_model", "value": EMBED_MODEL if embed else "none"},
        {"key": "synthetic", "value": "true"},
    ]
    return tables


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build ClinIQ Nexus v5 curated tables locally")
    ap.add_argument("--raw", default="data/v5/raw")
    ap.add_argument("--out", default="data/v5/processed")
    ap.add_argument("--embed", action="store_true", help="Compute embeddings with the Databricks endpoint")
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    client = None
    if args.embed:
        from databricks.sdk import WorkspaceClient
        client = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    result = process(args.raw, embed=args.embed, embed_client=client)
    os.makedirs(args.out, exist_ok=True)
    for name, rows in result.items():
        with open(os.path.join(args.out, f"{name}.json"), "w") as f:
            json.dump(rows, f)
    for c in result["integrity_checks"]:
        print(f"{c['check_id']} {c['status'].upper():4} {c['check_name']} ({c['failing_count']}/{c['checked_count']}) {c['detail'][:80]}")
    print({k: len(v) for k, v in result.items()})


def coerce(rows: list[dict], ddl: str) -> list[dict]:
    """Cast values to the declared Spark types (e.g. int -> float for DOUBLE columns)."""
    casts = {}
    for col in ddl.split(", "):
        name, typ = col.split(" ", 1)
        casts[name] = {"DOUBLE": float, "INT": int, "BIGINT": int, "STRING": str, "BOOLEAN": bool}.get(typ)
    out = []
    for r in rows:
        row = {}
        for name, fn in casts.items():
            v = r.get(name)
            row[name] = v if v is None or fn is None else fn(v)
        out.append(row)
    return out
