"""Clinical read models: patient bundle, record-derived brief, worklist and operations metrics.

Everything here is deterministic and derived from source records. Each brief item carries
evidence references so the UI can open the supporting record.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from statistics import median

from .datasource import get_source

ACUTE = {"EMER", "IMP"}


def parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    if len(ts) == 10:
        ts += "T00:00:00Z"
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def day(ts: str | None) -> str:
    d = parse(ts)
    return f"{d.day} {d.strftime('%b %Y')}" if d else ""


def short(ts: str | None) -> str:
    d = parse(ts)
    return f"{d.day} {d.strftime('%b')}" if d else ""


def num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def manifest() -> dict:
    rows = get_source().directory_rows("dataset_manifest")
    return {r["key"]: r["value"] for r in rows}


def as_of() -> datetime:
    return parse(manifest().get("as_of")) or datetime.now(timezone.utc)


def ref(kind: str, rid: str, label: str, date: str | None = None, page: int | None = None) -> dict:
    out = {"type": kind, "id": rid, "label": label}
    if date:
        out["date"] = date
    if page:
        out["page"] = page
    return out


# --------------------------------------------------------------------------- bundle

def patient_bundle(pid: str) -> dict:
    src = get_source()
    tables = ["patients", "encounters", "conditions", "observations", "medication_requests", "clinical_notes",
              "follow_up_items", "portal_threads", "portal_messages", "imaging_studies", "imaging_reports", "documents"]
    with ThreadPoolExecutor(max_workers=4) as pool:      # each read is its own patient-bound query
        rows = dict(zip(tables, pool.map(lambda t: src.patient_rows(t, pid), tables)))
    if not rows["patients"]:
        raise LookupError("Patient not found")
    msgs = defaultdict(list)
    for m in sorted(rows["portal_messages"], key=lambda m: m["sent_at"]):
        msgs[m["thread_id"]].append(m)
    threads = [dict(t, messages=msgs[t["thread_id"]]) for t in sorted(rows["portal_threads"], key=lambda t: t["last_message_at"], reverse=True)]
    reports = {r["study_id"]: r for r in rows["imaging_reports"]}
    imaging = [dict(s, report=reports.get(s["study_id"])) for s in sorted(rows["imaging_studies"], key=lambda s: s["study_at"])]
    bundle = {
        "patient": rows["patients"][0],
        "encounters": sorted(rows["encounters"], key=lambda e: e["start_at"]),
        "conditions": rows["conditions"],
        "observations": sorted(rows["observations"], key=lambda o: o["effective_at"]),
        "medications": sorted(rows["medication_requests"], key=lambda m: m["authored_on"]),
        "notes": sorted(rows["clinical_notes"], key=lambda n: n["authored_at"]),
        "follow_ups": rows["follow_up_items"],
        "threads": threads,
        "imaging": imaging,
        "documents": sorted(rows["documents"], key=lambda d: d["authored_at"]),
        "as_of": manifest().get("as_of"),
    }
    bundle["brief"] = build_brief(bundle)
    bundle["problems"] = problem_list(bundle["conditions"])
    return bundle


def problem_list(conditions: list[dict]) -> list[dict]:
    # Latest record per ICD-10 category (e.g. I50.23 acute-on-chronic superseded by a later I50.22 chronic code)
    latest: dict[str, dict] = {}
    for c in sorted(conditions, key=lambda c: c["recorded_at"]):
        latest[c["code"][:3]] = c
    order = {"active": 0, "resolved": 1}
    return sorted(latest.values(), key=lambda c: (order.get(c["clinical_status"], 2), c["display"]))


def latest_vitals(observations: list[dict]) -> list[dict]:
    series = defaultdict(list)
    for o in observations:
        series[o["measure_key"]].append(o)
    out = []
    for key in ["sbp", "hr", "spo2", "temp", "rr", "wt", "pain"]:
        s = series.get(key)
        if not s:
            continue
        last, prev = s[-1], (s[-2] if len(s) > 1 else None)
        item = {"key": key, "name": last["name"], "value": last["value"], "unit": last["display_unit"],
                "at": last["effective_at"], "observation_id": last["observation_id"], "count": len(s),
                "previous": prev["value"] if prev else None, "previous_at": prev["effective_at"] if prev else None}
        if key == "sbp":
            dia = next((o for o in series.get("dbp", []) if o["panel_id"] == last["panel_id"]), None)
            item["value_diastolic"] = dia["value"] if dia else None
            pdia = next((o for o in series.get("dbp", []) if prev and o["panel_id"] == prev["panel_id"]), None)
            item["previous_diastolic"] = pdia["value"] if pdia else None
        out.append(item)
    return out


def build_brief(b: dict) -> dict:
    now = parse(b["as_of"]) or datetime.now(timezone.utc)
    encs = b["encounters"]
    items: list[dict] = []
    docs_by_enc = defaultdict(list)
    for d in b["documents"]:
        docs_by_enc[d["encounter_id"]].append(d)

    # 1. Most recent acute-care episode (ED or inpatient) in the last 120 days
    acute = [e for e in encs if e["class_code"] in ACUTE and parse(e["end_at"]) >= now - timedelta(days=120)]
    if acute:
        last = acute[-1]
        episode = [e for e in acute if e["patient_id"] == last["patient_id"] and parse(last["start_at"]) - parse(e["end_at"]) <= timedelta(hours=1)]
        start = episode[0]["start_at"]
        title = ("Hospital admission" if last["class_code"] == "IMP" else "Emergency department visit")
        if last["status"] == "finished" and last["disposition"].lower().startswith("discharged"):
            title += " (discharged)"
        when = f"{short(start)} – {short(last['end_at'])}" if day(start) != day(last["end_at"]) else day(start)
        refs = [ref("encounter", e["encounter_id"], f"{e['encounter_type']} · {day(e['start_at'])}", e["start_at"]) for e in episode]
        for d in docs_by_enc.get(last["encounter_id"], []):
            if d["doc_kind"] == "discharge_summary":
                refs.append(ref("document", d["document_id"], f"{d['title']} · {day(d['authored_at'])}", d["authored_at"], 1))
        items.append({"id": "acute", "kind": "acute_care", "severity": "attention", "title": f"{title} · {when}",
                      "detail": f"{last['reason']}. {last['disposition']}.", "date": last["end_at"], "refs": refs})

    # 2. Portal threads awaiting a reply, and routed requests still pending
    for t in b["threads"]:
        if t["status"] not in ("awaiting_reply", "routed"):
            continue
        waited = (now - parse(t["last_message_at"])).days
        age = "today" if waited < 1 else f"{waited} day{'s' if waited != 1 else ''}"
        last_patient = next((m for m in reversed(t["messages"]) if m["sender_role"] == "patient"), None)
        if t["status"] == "awaiting_reply":
            items.append({"id": f"thread-{t['thread_id']}", "kind": "awaiting_reply", "severity": "attention",
                          "title": f"Portal message awaiting reply · {age}", "detail": f"“{last_patient['message_body']}”",
                          "date": t["last_message_at"], "refs": [ref("thread", t["thread_id"], f"Portal thread · {t['subject']}", t["opened_at"])]})
        else:
            items.append({"id": f"thread-{t['thread_id']}", "kind": "routed", "severity": "info",
                          "title": f"Routed request pending · {age}",
                          "detail": f"{t['subject']} — routed to {t['routed_to']}; no completion documented.",
                          "date": t["last_message_at"], "refs": [ref("thread", t["thread_id"], f"Portal thread · {t['subject']}", t["opened_at"])]})

    # 3. Medication changes in the 45 days before the latest record
    window = now - timedelta(days=45)
    changes = []
    replaced = {m["prior_request_id"] for m in b["medications"] if m["prior_request_id"]}
    for m in b["medications"]:
        if m["category"] in ("inpatient", "home"):
            continue
        authored = parse(m["authored_on"])
        if authored >= window and m["action"] in ("started", "changed"):
            verb = "Started" if m["action"] == "started" else "Changed"
            changes.append((authored, f"{verb} {m['medication']} {m['dose']} {m['frequency']}", m))
    for m in b["medications"]:
        if m["status"] == "stopped" and m["medication_request_id"] not in replaced and m["category"] != "inpatient":
            ended = parse(m["end_date"])
            if ended and ended >= window:
                changes.append((ended, f"Stopped {m['medication']} {m['dose']}", m))
    if changes:
        changes.sort(key=lambda c: c[0])
        items.append({"id": "meds", "kind": "medication_changes", "severity": "info",
                      "title": f"{len(changes)} medication change{'s' if len(changes) > 1 else ''} since {short(window.isoformat())}",
                      "detail": "; ".join(c[1] for c in changes) + ".", "date": changes[-1][0].isoformat(),
                      "refs": [ref("medication", c[2]["medication_request_id"], f"{c[1]} · {day(c[0].isoformat())}", c[0].isoformat()) for c in changes]})

    # 4. Latest laboratory values outside the reference range
    labs = defaultdict(list)
    for o in b["observations"]:
        if o["category"] == "laboratory":
            labs[o["measure_key"]].append(o)
    flagged = []
    for key, series in labs.items():
        last = series[-1]
        if last["interpretation"] in ("H", "L"):
            prev = series[-2] if len(series) > 1 else None
            trend = f" (previous {num(prev['value'])} on {short(prev['effective_at'])})" if prev else ""
            flagged.append((last, f"{last['name']} {num(last['value'])} {last['display_unit']} {last['interpretation']}{trend}"))
    if flagged:
        flagged.sort(key=lambda f: f[0]["effective_at"], reverse=True)
        items.append({"id": "labs", "kind": "abnormal_results", "severity": "info",
                      "title": "Latest results outside reference range", "detail": "; ".join(f[1] for f in flagged) + ".",
                      "date": flagged[0][0]["effective_at"],
                      "refs": [ref("observation", f[0]["observation_id"], f"{f[0]['name']} · {day(f[0]['effective_at'])}", f[0]["effective_at"]) for f in flagged]})

    # 5. Follow-up items without documented completion
    open_items = [f for f in b["follow_ups"] if f["status"] == "open"]
    overdue = [f for f in open_items if f["due_date"] and parse(f["due_date"]) < now]
    for f in sorted(overdue, key=lambda f: f["due_date"]):
        items.append({"id": f"fu-{f['follow_up_id']}", "kind": "overdue_follow_up", "severity": "attention",
                      "title": f"Follow-up past due date · due {day(f['due_date'])}",
                      "detail": f"{f['description']} — no completion documented.", "date": f["due_date"],
                      "refs": [ref("note", f["source_note_id"], "Documented in note", None), ref("follow_up", f["follow_up_id"], f["description"], f["due_date"])]})

    # 6. Scanned documents that cannot be searched
    scanned = [d for d in b["documents"] if not d["has_text_layer"]]
    if scanned:
        items.append({"id": "scanned", "kind": "unsearchable_documents", "severity": "info",
                      "title": f"{len(scanned)} scanned document{'s' if len(scanned) > 1 else ''} not machine-readable",
                      "detail": "No text layer; OCR not performed. Open the PDF to review: " + ", ".join(d["title"] for d in scanned) + ".",
                      "date": scanned[-1]["authored_at"],
                      "refs": [ref("document", d["document_id"], f"{d['title']} · {day(d['authored_at'])}", d["authored_at"], 1) for d in scanned]})

    sev = {"attention": 0, "info": 1}
    items.sort(key=lambda i: (sev[i["severity"]], -(parse(i["date"]) or now).timestamp()))
    last_enc = encs[-1] if encs else None
    upcoming = sorted([f for f in b["follow_ups"] if f["status"] == "scheduled" and f["due_date"] and parse(f["due_date"]) >= now],
                      key=lambda f: f["due_date"])
    active = [e for e in encs if e["status"] in ("in-progress", "arrived", "triaged", "onleave")]
    return {
        "items": items,
        "active_encounter": active[-1] if active else None,
        "last_encounter": last_enc,
        "days_since_last_encounter": (now - parse(last_enc["end_at"])).days if last_enc else None,
        "vitals": latest_vitals(b["observations"]),
        "upcoming": upcoming[:3],
        "counts": {"encounters": len(encs), "notes": len(b["notes"]), "documents": len(b["documents"]),
                   "pages": sum(d["page_count"] for d in b["documents"]),
                   "messages": sum(len(t["messages"]) for t in b["threads"]), "threads": len(b["threads"]),
                   "imaging": len(b["imaging"]), "observations": len(b["observations"]),
                   "active_medications": sum(1 for m in b["medications"] if m["status"] == "active")},
    }


# --------------------------------------------------------------------------- worklist

def worklist() -> list[dict]:
    src = get_source()
    now = as_of()
    patients = src.directory_rows("patients")
    encs, threads = defaultdict(list), defaultdict(list)
    for e in src.directory_rows("encounters"):
        encs[e["patient_id"]].append(e)
    for t in src.directory_rows("portal_threads"):
        threads[t["patient_id"]].append(t)
    fus = defaultdict(list)
    for f in src.directory_rows("follow_up_items"):
        fus[f["patient_id"]].append(f)
    docs = Counter(d["patient_id"] for d in src.directory_rows("documents"))
    imgs = Counter(s["patient_id"] for s in src.directory_rows("imaging_studies"))
    out = []
    for p in sorted(patients, key=lambda p: p["patient_id"]):
        pe = sorted(encs[p["patient_id"]], key=lambda e: e["start_at"])
        last = pe[-1] if pe else None
        acute = [e for e in pe if e["class_code"] in ACUTE and parse(e["end_at"]) >= now - timedelta(days=120)]
        out.append({
            "patient_id": p["patient_id"], "display_name": p["display_name"], "sex": p["sex"], "age_years": p["age_years"],
            "mrn": p["mrn"], "care_program": p["care_program"], "primary_clinician": p["primary_clinician"],
            "last_encounter_at": last["start_at"] if last else None, "last_encounter_type": last["encounter_type"] if last else None,
            "last_encounter_class": last["class_code"] if last else None,
            "recent_acute_at": acute[-1]["end_at"] if acute else None, "recent_acute_class": acute[-1]["class_code"] if acute else None,
            "awaiting_reply": sum(1 for t in threads[p["patient_id"]] if t["status"] == "awaiting_reply"),
            "routed_pending": sum(1 for t in threads[p["patient_id"]] if t["status"] == "routed"),
            "overdue_follow_ups": sum(1 for f in fus[p["patient_id"]] if f["status"] == "open" and f["due_date"] and parse(f["due_date"]) < now),
            "documents": docs[p["patient_id"]], "imaging": imgs[p["patient_id"]], "encounters": len(pe),
        })
    return out


# --------------------------------------------------------------------------- operations

def operations() -> dict:
    src = get_source()
    encs = src.directory_rows("encounters")
    notes = src.directory_rows("clinical_notes")
    docs = src.directory_rows("documents")
    threads = src.directory_rows("portal_threads")
    studies = src.directory_rows("imaging_studies")
    reports = src.directory_rows("imaging_reports")
    checks = src.directory_rows("integrity_checks")
    quarantine = src.directory_rows("document_quarantine")
    chunks = src.directory_rows("knowledge_chunks")
    now = as_of()

    by_month = defaultdict(Counter)
    for e in encs:
        by_month[e["start_at"][:7]][e["class_code"]] += 1
    noted = {n["encounter_id"] for n in notes}
    inpatient = [e for e in encs if e["class_code"] == "IMP"]
    ds_encs = {d["encounter_id"] for d in docs if d["doc_kind"] == "discharge_summary"}
    responded = [t["first_response_minutes"] for t in threads if t["first_response_minutes"] is not None]
    awaiting = [t for t in threads if t["status"] == "awaiting_reply"]
    report_ids = {r["study_id"] for r in reports}
    return {
        "as_of": now.isoformat(),
        "totals": {"patients": len({e["patient_id"] for e in encs}), "encounters": len(encs), "notes": len(notes),
                   "documents": len(docs), "pages": sum(d["page_count"] for d in docs), "threads": len(threads),
                   "imaging": len(studies), "chunks": len(chunks)},
        "encounters": {
            "by_class": dict(Counter(e["class_code"] for e in encs)),
            "by_month": [{"month": m, **dict(c)} for m, c in sorted(by_month.items())],
            "by_service": dict(Counter(e["service"] for e in encs).most_common()),
            "inpatient_los_days": [round(e["duration_hours"] / 24, 1) for e in inpatient],
        },
        "documentation": {
            "encounters_with_note_pct": round(100 * len(noted & {e["encounter_id"] for e in encs}) / max(len(encs), 1)),
            "admissions_with_discharge_summary": f"{len(ds_encs & {e['encounter_id'] for e in inpatient})}/{len(inpatient)}",
            "documents_by_type": dict(Counter(d["doc_type"] for d in docs).most_common()),
            "text_layer": sum(1 for d in docs if d["has_text_layer"]), "scanned": sum(1 for d in docs if not d["has_text_layer"]),
            "verified": sum(1 for d in docs if d["identity_status"] == "verified"),
            "quarantined": len(quarantine),
            "quarantine": [{"document_id": q["document_id"], "reason": q["reason"], "detected_at": q["detected_at"]} for q in quarantine],
        },
        "communications": {
            "by_status": dict(Counter(t["status"] for t in threads)),
            "by_category": dict(Counter(t["category"] for t in threads).most_common()),
            "first_response_minutes": sorted(responded),
            "median_first_response_hours": round(median(responded) / 60, 1) if responded else None,
            "awaiting": sorted([{"thread_id": t["thread_id"], "patient_id": t["patient_id"], "subject": t["subject"],
                                 "waiting_days": (now - parse(t["last_message_at"])).days, "category": t["category"]} for t in awaiting],
                               key=lambda a: -a["waiting_days"]),
        },
        "imaging": {
            "studies": len(studies), "with_report": sum(1 for s in studies if s["study_id"] in report_ids),
            "header_verified": sum(1 for s in studies if s.get("dicom_header_verified")),
            "by_procedure": dict(Counter(s["ordered_procedure"] for s in studies).most_common()),
        },
        "retrieval": {"by_source": dict(Counter(c["source_type"] for c in chunks))},
        "quality": sorted(checks, key=lambda c: c["check_id"]),
        "manifest": manifest(),
    }
