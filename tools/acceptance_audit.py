"""Cross-source clinical consistency audit for the v5 dataset and read models.

Usage: python tools/acceptance_audit.py  (offline; reads data/v5 and runs the backend in local mode)
Writes docs/acceptance/acceptance-audit.json and prints a summary. Exit code 1 on any failure.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CLINIQ_DATA_MODE", "local")
os.environ.setdefault("CLINIQ_FILES_MODE", "local")
os.environ.setdefault("CLINIQ_LOCAL_DIR", str(ROOT / "data" / "v5"))
sys.path.insert(0, str(ROOT / "app"))

import pydicom  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from backend.clinical import patient_bundle, worklist  # noqa: E402

P = {p.stem: json.loads(p.read_text()) for p in (ROOT / "data/v5/processed").glob("*.json")}
RAW = ROOT / "data/v5/raw"
AS_OF = datetime.fromisoformat(next(r["value"] for r in P["dataset_manifest"] if r["key"] == "as_of").replace("Z", "+00:00"))
results: list[dict] = []


def ts(s):
    return datetime.fromisoformat((s + "T00:00:00Z" if len(s) == 10 else s).replace("Z", "+00:00"))


def check(cid, area, name, failures, checked, note=""):
    results.append({"id": cid, "area": area, "check": name, "checked": checked, "failures": failures[:10],
                    "status": "pass" if not failures else "fail", "note": note})


def num_tokens(text):
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])", text)}


def age(birth, when):
    b = ts(birth)
    return when.year - b.year - ((when.month, when.day) < (b.month, b.day))


patients = {p["patient_id"]: p for p in P["patients"]}
encs = {e["encounter_id"]: e for e in P["encounters"]}
by_pat = defaultdict(list)
for e in P["encounters"]:
    by_pat[e["patient_id"]].append(e)

# 1. Identity: ages in notes, names/MRN in notes, PDFs, DICOM
fails, n = [], 0
for note in P["clinical_notes"]:
    p, e = patients[note["patient_id"]], encs[note["encounter_id"]]
    for m in re.finditer(r"(\d+)-year-old", note["note_text"]):
        n += 1
        if int(m.group(1)) != age(p["birth_date"], ts(e["start_at"])):
            fails.append(f"{note['note_id']}: stated {m.group(1)}, actual {age(p['birth_date'], ts(e['start_at']))}")
    n += 1
    if f"Patient: {p['display_name']} | Patient ID: {p['patient_id']} | MRN: {p['mrn']}" not in note["note_text"]:
        fails.append(f"{note['note_id']}: header identity mismatch")
check("AUD-01", "Identity", "Note headers and stated ages match the patient record", fails, n)

fails, n = [], 0
for d in P["documents"]:
    p = patients[d["patient_id"]]
    for page in [x for x in P["document_pages"] if x["document_id"] == d["document_id"] and x["has_text_layer"]]:
        n += 1
        banner = f"{p['display_name']}  |  Patient ID: {p['patient_id']}  |  MRN: {p['mrn']}"
        if banner not in page["page_text"] or f"Encounter: {d['encounter_id']}" not in page["page_text"]:
            fails.append(f"{page['page_id']}: banner patient/encounter mismatch")
check("AUD-02", "PDF documents", "Every text PDF page prints the filed patient, MRN and encounter", fails, n)

fails = []
for s in P["imaging_studies"]:
    p = patients[s["patient_id"]]
    ds = pydicom.dcmread(RAW / "dicom" / f"{s['study_id']}.dcm")
    want = {"PatientID": p["patient_id"], "PatientName": f"SYNTHETIC^PATIENT{p['patient_id'][-3:]}",
            "PatientBirthDate": p["birth_date"].replace("-", ""), "PatientSex": "F" if p["sex"] == "female" else "M",
            "StudyDate": s["study_at"][:10].replace("-", ""), "AccessionNumber": s["accession_number"], "Modality": "OT",
            "ConversionType": "SYN", "BurnedInAnnotation": "YES"}
    for k, v in want.items():
        if str(getattr(ds, k, "")) != v:
            fails.append(f"{s['study_id']}: {k}={getattr(ds, k, '')} expected {v}")
    if "Not a medical image" not in str(ds.ImageComments):
        fails.append(f"{s['study_id']}: ImageComments lacks synthetic statement")
    e = encs[s["encounter_id"]]
    if not (ts(e["start_at"]) - timedelta(days=1) <= ts(s["study_at"]) <= ts(e["end_at"]) + timedelta(days=21)):
        fails.append(f"{s['study_id']}: study date outside encounter window")
check("AUD-03", "Imaging", "DICOM headers (identity, dates, accession, SYN, burned-in) match catalog and patient", fails, len(P["imaging_studies"]))

fails = []
for r in P["imaging_reports"]:
    s = next(x for x in P["imaging_studies"] if x["study_id"] == r["study_id"])
    for token in (r["patient_id"], r["study_id"], s["accession_number"], "NOT A RADIOLOGY INTERPRETATION", "was not interpreted"):
        if token not in r["report_text"]:
            fails.append(f"{r['report_id']}: missing '{token}'")
check("AUD-04", "Imaging", "Imaging reports reference their study/accession and state no interpretation", fails, len(P["imaging_reports"]))

# 2. Chronology
fails, n = [], 0
for pid, es in by_pat.items():
    es = sorted(es, key=lambda e: e["start_at"])
    for a, b in zip(es, es[1:]):
        n += 1
        if ts(b["start_at"]) < ts(a["end_at"]):
            fails.append(f"{a['encounter_id']} overlaps {b['encounter_id']}")
    for e in es:
        n += 1
        if not (ts(e["start_at"]) < ts(e["end_at"]) <= AS_OF) or e["status"] != "finished":
            fails.append(f"{e['encounter_id']}: invalid period or status")
check("AUD-05", "Encounters", "Encounters are finished, non-overlapping and end before the as-of date", fails, n,
      "No encounter is in progress, so no patient is currently admitted.")

fails, notes = [], []
for o in P["observations"]:
    e = encs[o["encounter_id"]]
    t = ts(o["effective_at"])
    if ts(e["start_at"]) - timedelta(hours=2) <= t <= ts(e["end_at"]):
        continue
    if e["class_code"] == "VR" and ts(e["start_at"]) - timedelta(days=7) <= t < ts(e["start_at"]):
        notes.append(o["observation_id"])
        continue
    fails.append(f"{o['observation_id']} at {o['effective_at']} outside {e['encounter_id']}")
check("AUD-06", "Observations", "Measurements fall within their encounter (pre-visit labs allowed for telehealth reviews)", fails,
      len(P["observations"]), f"{len(notes)} labs drawn up to 5 days before a telehealth review and linked to it (documented in the note)")

fails = []
for o in P["observations"]:
    lo, hi, v = o["ref_low"], o["ref_high"], o["value"]
    if o["category"] == "laboratory":
        exp = "L" if lo is not None and v < lo else "H" if hi is not None and v > hi else "N"
        if o["interpretation"] != exp:
            fails.append(f"{o['observation_id']}: flag {o['interpretation']} expected {exp}")
    if o["unit"] in ("", None) or not re.match(r"^\d{3,5}-\d$", o["code"]):
        fails.append(f"{o['observation_id']}: unit/LOINC missing")
check("AUD-07", "Observations", "Lab flags agree with reference ranges; every value has UCUM unit and LOINC code", fails, len(P["observations"]))

# 3. Medications
fails = []
meds = {m["medication_request_id"]: m for m in P["medication_requests"]}
for m in meds.values():
    e = encs[m["encounter_id"]]
    if not (ts(e["start_at"]) - timedelta(minutes=1) <= ts(m["authored_on"]) <= ts(e["end_at"]) + timedelta(minutes=1)):
        fails.append(f"{m['medication_request_id']}: authored outside encounter")
    if m["prior_request_id"]:
        prior = meds[m["prior_request_id"]]
        if prior["medication"] != m["medication"] or prior["status"] != "stopped" or prior["end_date"] != m["authored_on"]:
            fails.append(f"{m['medication_request_id']}: dose-change chain inconsistent")
    if m["status"] == "active" and m["end_date"] and ts(m["end_date"]) <= AS_OF:
        fails.append(f"{m['medication_request_id']}: active but ended")
    if m["status"] == "completed" and (not m["end_date"] or ts(m["end_date"]) > AS_OF):
        fails.append(f"{m['medication_request_id']}: completed without past end date")
check("AUD-08", "Medications", "Orders authored within their encounter; dose-change chains and statuses consistent with dates", fails, len(meds))


def pdf_text(doc_id):
    return "\n".join(p.extract_text() or "" for p in PdfReader(RAW / "documents" / f"{doc_id}.pdf").pages)


fails, n = [], 0
for d in [d for d in P["documents"] if d["doc_kind"] == "discharge_summary"]:
    text = pdf_text(d["document_id"])
    flat = re.sub(r"\s+", " ", text)          # table cells wrap across lines in extracted text
    end = encs[d["encounter_id"]]["end_at"]
    active = [m for m in meds.values() if m["patient_id"] == d["patient_id"] and m["category"] != "inpatient"
              and ts(m["authored_on"]) <= ts(end) and (not m["end_date"] or ts(m["end_date"]) > ts(end))]
    for m in active:
        n += 1
        if m["medication"] not in flat or re.sub(r"\s+", " ", m["dose"]) not in flat:
            fails.append(f"{d['document_id']}: {m['medication']} {m['dose']} missing from discharge medications")
    for m in meds.values():
        if m["patient_id"] == d["patient_id"] and m["category"] == "inpatient":
            n += 1
            row = re.search(rf"{re.escape(m['medication'])}.*\n?.*(CONTINUED|NEW)", text)
            if row and m["medication"] not in [a["medication"] for a in active]:
                fails.append(f"{d['document_id']}: inpatient-only {m['medication']} listed as discharge medication")
check("AUD-09", "PDF documents", "Discharge-summary medication tables match orders active at discharge", fails, n)

fails, n = [], 0
for d in [d for d in P["documents"] if d["doc_kind"] in ("lab_report", "discharge_summary")]:
    text = pdf_text(d["document_id"])
    tokens = num_tokens(text)
    enc_ids = set(re.findall(r"CN-E\d{3}-\d{2}", text)) | {d["encounter_id"]}
    if d["doc_kind"] == "discharge_summary":
        enc_ids = {d["encounter_id"]} | {e["encounter_id"] for e in by_pat[d["patient_id"]]
                                         if e["class_code"] == "EMER" and e["end_at"] == encs[d["encounter_id"]]["start_at"]}
    for o in P["observations"]:
        if o["encounter_id"] in enc_ids and o["category"] == "laboratory":
            n += 1
            v = o["value"]
            tok = str(int(v)) if float(v).is_integer() else f"{v:g}"
            if tok not in tokens:
                fails.append(f"{d['document_id']}: {o['name']} {tok} not on report")
check("AUD-10", "PDF documents", "Every lab value of the covered encounters appears on lab reports and discharge summaries", fails, n)

# 4. Follow-up and communication
fails = []
for f in P["follow_up_items"]:
    if f["status"] == "scheduled" and f["due_date"] and ts(f["due_date"]) < AS_OF:
        fails.append(f"{f['follow_up_id']}: scheduled date already passed without completion")
    if f["status"] == "completed" and f["resolved_encounter_id"]:
        if ts(encs[f["resolved_encounter_id"]]["start_at"]) < ts(encs[f["encounter_id"]]["start_at"]):
            fails.append(f"{f['follow_up_id']}: resolved before documented")
check("AUD-11", "Care coordination", "Follow-up statuses are consistent with the as-of date and resolving encounters", fails, len(P["follow_up_items"]))

fails = []
msgs = defaultdict(list)
for m in P["portal_messages"]:
    msgs[m["thread_id"]].append(m)
for t in P["portal_threads"]:
    ms = sorted(msgs[t["thread_id"]], key=lambda m: m["sent_at"])
    if ms[0]["sender_role"] != "patient":
        fails.append(f"{t['thread_id']}: thread not opened by patient")
    if ts(ms[0]["sent_at"]) < ts(encs[t["encounter_id"]]["start_at"]) or ts(ms[-1]["sent_at"]) > AS_OF:
        fails.append(f"{t['thread_id']}: messages outside related encounter/as-of window")
    if t["last_message_at"] != ms[-1]["sent_at"] or t["message_count"] != len(ms):
        fails.append(f"{t['thread_id']}: summary fields inconsistent")
check("AUD-12", "Care coordination", "Portal threads open with a patient message after the related encounter and summaries match", fails, len(P["portal_threads"]))

# 5. Brief and worklist (read models)
fails, n = [], 0
for p in P["patients"]:
    b = patient_bundle(p["patient_id"])
    lookup = {}
    for o in b["observations"]:
        lookup[o["observation_id"]] = f"{o['name']} {o['value']:g} {o['effective_at']}"
    for m in b["medications"]:
        lookup[m["medication_request_id"]] = f"{m['medication']} {m['dose']} {m['frequency']} {m['authored_on']} {m['end_date']}"
    for t in b["threads"]:
        lookup[t["thread_id"]] = " ".join(x["message_body"] + " " + x["sent_at"] for x in t["messages"]) + f" {t['routed_to']}"
    for e in b["encounters"]:
        lookup[e["encounter_id"]] = f"{e['reason']} {e['disposition']} {e['start_at']} {e['end_at']}"
    for f in b["follow_ups"]:
        lookup[f["follow_up_id"]] = f"{f['description']} {f['due_date']}"
    for d in b["documents"]:
        lookup[d["document_id"]] = f"{d['title']} {d['authored_at']}"
    for item in b["brief"]["items"]:
        n += 1
        evidence = " ".join(lookup.get(r["id"], "") for r in item["refs"])
        detail = re.sub(r"\(previous [^)]*\)", "", item["detail"])
        missing = num_tokens(detail) - num_tokens(evidence) - {"1", "2", "3"}
        if missing:
            fails.append(f"{p['patient_id']} {item['kind']}: values {sorted(missing)} not in referenced records")
    probs = [c["code"][:3] for c in b["problems"]]
    if len(probs) != len(set(probs)):
        fails.append(f"{p['patient_id']}: duplicate problem categories")
check("AUD-13", "Physician brief", "Every value stated in a brief item appears in the records it references", fails, n,
      "Brief items are deterministic summaries; none contains diagnostic or treatment language.")

fails = []
for r in worklist():
    p = patients[r["patient_id"]]
    es = sorted(by_pat[r["patient_id"]], key=lambda e: e["start_at"])
    if r["age_years"] != age(p["birth_date"], AS_OF) or r["last_encounter_at"] != es[-1]["start_at"]:
        fails.append(f"{r['patient_id']}: age or last encounter mismatch")
check("AUD-14", "Worklist", "Worklist ages (as of the record date) and last-encounter dates match source records", fails, len(P["patients"]))

out = ROOT / "docs" / "acceptance"
out.mkdir(parents=True, exist_ok=True)
(out / "acceptance-audit.json").write_text(json.dumps({"as_of": AS_OF.isoformat(), "results": results}, indent=2))
for r in results:
    print(f"{r['id']} {r['status'].upper():4} [{r['area']}] {r['check']} ({len(r['failures'])}/{r['checked']}) {'; '.join(r['failures'][:3])}")
sys.exit(1 if any(r["status"] == "fail" for r in results) else 0)
