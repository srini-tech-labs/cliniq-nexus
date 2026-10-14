"""Build structured v5 records (FHIR R4-style, flattened) from the authored scenarios."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from catalog import ENCOUNTER_CLASS, LABS, VITALS, interpret, ref_range
from scenarios import AS_OF, CLINICIANS, HOSPITAL, PATIENTS

VOLUME_ROOT = "/Volumes/healthcare/cliniq_v5_stage/raw/v5"
DISCLAIMER = "SYNTHETIC DEMONSTRATION RECORD — NOT FOR CLINICAL USE"


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"


def fmt_dt(dt: datetime) -> str:
    return f"{fmt_date(dt)} {dt.strftime('%H:%M')} UTC"


def fmt_num(value) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def pnum(patient_id: str) -> str:
    return patient_id.split("-P")[1]


def age_at(birth: str, when: datetime) -> int:
    b = datetime.fromisoformat(birth)
    return when.year - b.year - ((when.month, when.day) < (b.month, b.day))


def display_name(patient_id: str) -> str:
    return f"Synthetic Patient {pnum(patient_id)}"


def mrn(patient_id: str) -> str:
    return f"SYN-{int(pnum(patient_id)):06d}"


def enc_id(patient_id: str, key: str) -> str:
    return f"CN-E{pnum(patient_id)}-{key}"


def vital_line(v: dict) -> str:
    parts = []
    if "temp" in v: parts.append(f"Temp {fmt_num(v['temp'])} °C")
    if "hr" in v: parts.append(f"HR {fmt_num(v['hr'])} bpm")
    if "rr" in v: parts.append(f"RR {fmt_num(v['rr'])} breaths/min")
    if "spo2" in v: parts.append(f"SpO2 {fmt_num(v['spo2'])}%")
    if "sbp" in v: parts.append(f"BP {fmt_num(v['sbp'])}/{fmt_num(v['dbp'])} mmHg")
    if "wt" in v: parts.append(f"Weight {fmt_num(v['wt'])} kg")
    if "pain" in v: parts.append(f"Pain {fmt_num(v['pain'])}/10")
    return ", ".join(parts)


def lab_line(lab: dict, sex: str) -> str:
    parts = []
    for key, value in lab.items():
        if key == "ts":
            continue
        spec = LABS[key]
        flag = interpret(key, value, sex)
        parts.append(f"{spec['name']} {fmt_num(value)} {spec['display_unit']}" + (f" ({flag})" if flag != "N" else ""))
    return "; ".join(parts)


def build_all():
    out = {k: [] for k in ["patients", "encounters", "conditions", "observations", "medication_requests",
                           "clinical_notes", "follow_up_items", "portal_threads", "portal_messages",
                           "imaging_studies", "imaging_reports", "document_index"]}
    as_of = ts(AS_OF)
    for p in PATIENTS:
        build_patient(p, out, as_of)
    return out


def sig(m: dict) -> str:
    return f"{m['medication']} {m['dose']} {m['route']} {m['frequency']}"


def build_patient(p: dict, out: dict, as_of: datetime) -> None:
    pid, n = p["id"], pnum(p["id"])
    encs = {e["key"]: e for e in p["encounters"]}
    out["patients"].append({
        "patient_id": pid, "display_name": display_name(pid), "mrn": mrn(pid), "sex": p["sex"],
        "birth_date": p["birth_date"], "age_years": age_at(p["birth_date"], as_of),
        "primary_clinician": CLINICIANS[p["pcp"]], "care_program": p["program"],
        "program_summary": p["summary"], "is_synthetic": True,
    })

    obs_seq = cond_seq = med_seq = fu_seq = 0
    meds: dict[str, dict] = {}       # key -> current request
    note_ids: dict[str, str] = {}

    for e in p["encounters"]:
        eid = enc_id(pid, e["key"])
        start, end = ts(e["start"]), ts(e["end"])
        out["encounters"].append({
            "encounter_id": eid, "patient_id": pid, "status": "finished",
            "class_code": e["cls"], "class_display": ENCOUNTER_CLASS[e["cls"]],
            "encounter_type": e["type"], "service": e["service"],
            "attending": CLINICIANS[e["clinician"]], "location": HOSPITAL,
            "reason": e["reason"], "disposition": e["disposition"],
            "start_at": iso(start), "end_at": iso(end),
            "duration_hours": round((end - start).total_seconds() / 3600, 1), "is_synthetic": True,
        })
        for code, disp, status in e["dx"]:
            cond_seq += 1
            out["conditions"].append({
                "condition_id": f"CN-C{n}-{cond_seq:02d}", "patient_id": pid, "encounter_id": eid,
                "code_system": "ICD-10-CM", "code": code, "display": disp, "clinical_status": status,
                "category": "encounter-diagnosis", "recorded_at": iso(end), "is_synthetic": True,
            })
        for v in e["vitals"]:
            panel = f"CN-BP{n}-{obs_seq + 1:03d}" if "sbp" in v else None
            for key in ["temp", "hr", "rr", "spo2", "sbp", "dbp", "wt", "pain"]:
                if key not in v:
                    continue
                obs_seq += 1
                spec = VITALS[key]
                low, high = ref_range(key, p["sex"])
                out["observations"].append({
                    "observation_id": f"CN-O{n}-{obs_seq:03d}", "patient_id": pid, "encounter_id": eid,
                    "category": "vital-signs", "code_system": "LOINC", "code": spec["code"], "measure_key": key,
                    "name": spec["name"], "value": float(v[key]), "unit": spec["unit"], "display_unit": spec["display_unit"],
                    "ref_low": low, "ref_high": high, "interpretation": None,
                    "panel_id": panel if key in ("sbp", "dbp") else None,
                    "effective_at": iso(ts(v["ts"])), "is_synthetic": True,
                })
        for lab in e["labs"]:
            for key, value in lab.items():
                if key == "ts":
                    continue
                obs_seq += 1
                spec = LABS[key]
                low, high = ref_range(key, p["sex"])
                out["observations"].append({
                    "observation_id": f"CN-O{n}-{obs_seq:03d}", "patient_id": pid, "encounter_id": eid,
                    "category": "laboratory", "code_system": "LOINC", "code": spec["code"], "measure_key": key,
                    "name": spec["name"], "value": float(value), "unit": spec["unit"], "display_unit": spec["display_unit"],
                    "ref_low": low, "ref_high": high, "interpretation": interpret(key, value, p["sex"]),
                    "panel_id": None, "effective_at": iso(ts(lab["ts"])), "is_synthetic": True,
                })

        # Medication actions (state machine keyed by scenario med key)
        med_lines = []
        for a in e["meds"]:
            if a["action"] in ("start", "change"):
                med_seq += 1
                if a["action"] == "start":
                    if a["category"] == "home":
                        authored, category, action = start, "home", "reported"
                    elif a["setting"] == "inpatient":
                        authored, category, action = start, "inpatient", "started"
                    else:
                        authored = end if e["cls"] == "IMP" else start
                        category = "discharge" if e["cls"] == "IMP" else "outpatient"
                        action = "started"
                    base = {"medication": a["name"], "route": a["route"], "reason": a["reason"]}
                    dose, freq, prior = a["dose"], a["freq"], None
                    days = a["days"]
                else:
                    old = meds[a["key"]]
                    old["status"] = "stopped"
                    old["end_date"] = iso(start)
                    old["stop_reason"] = f"Dose changed: {a['reason']}"
                    authored, category, action = start, old["category"] if old["category"] != "home" else "outpatient", "changed"
                    base = {"medication": old["medication"], "route": old["route"], "reason": a["reason"]}
                    dose, freq, prior, days = a["dose"], a["freq"] or old["frequency"], old["medication_request_id"], None
                end_date = authored + timedelta(days=days) if days else None
                req = {
                    "medication_request_id": f"CN-M{n}-{med_seq:02d}", "patient_id": pid, "encounter_id": eid,
                    "medication": base["medication"], "dose": dose, "route": base["route"], "frequency": freq,
                    "category": category, "action": action, "status": "active",
                    "authored_on": iso(authored), "end_date": iso(end_date) if end_date else None,
                    "prior_request_id": prior, "reason": base["reason"], "stop_reason": None,
                    "prescriber": CLINICIANS[e["clinician"]] if category != "home" else None, "is_synthetic": True,
                }
                meds[a["key"]] = req
                out["medication_requests"].append(req)
                verb = {"reported": "Home medication documented", "started": "Started", "changed": "Changed to"}[action]
                course = f" for {days} days" if days else ""
                med_lines.append(f"{verb}: {req['medication']} {dose} {req['route']} {freq}{course}.")
            elif a["action"] == "stop":
                old = meds[a["key"]]
                old["status"] = "stopped"
                old["end_date"] = iso(start if a["at"] == "start" else end)
                old["stop_reason"] = a["reason"]
                med_lines.append(f"Stopped: {old['medication']} {old['dose']} — {a['reason']}.")

        # Follow-up items documented at this encounter
        fus = []
        for f in e.get("followups", []):
            fu_seq += 1
            item = {
                "follow_up_id": f"CN-F{n}-{fu_seq:02d}", "patient_id": pid, "encounter_id": eid,
                "description": f["text"], "due_date": f["due"], "status": f["status"],
                "resolved_encounter_id": enc_id(pid, f["resolved_by"]) if f["resolved_by"] else None,
                "source_note_id": None, "is_synthetic": True,
            }
            fus.append(item)
            out["follow_up_items"].append(item)

        # Clinical note rendered from structured facts + authored narrative
        note = e["note"]
        note_id = f"CN-N{n}-{e['key']}"
        note_ids[e["key"]] = note_id
        for item in fus:
            item["source_note_id"] = note_id
        sections = [("REASON FOR VISIT", e["reason"]), ("HISTORY", note["hpi"])]
        if e["vitals"]:
            sections.append(("VITAL SIGNS", "\n".join(f"{fmt_dt(ts(v['ts']))}: {vital_line(v)}" for v in e["vitals"])))
        if e["labs"]:
            sections.append(("RESULTS", "\n".join(f"{fmt_dt(ts(l['ts']))}: {lab_line(l, p['sex'])}" for l in e["labs"])))
        sections.append(("EXAMINATION", note["exam"]))
        sections.append(("ASSESSMENT", note["assessment"]))
        sections.append(("PLAN", "\n".join(f"- {line}" for line in note["plan"])))
        if med_lines:
            sections.append(("MEDICATION CHANGES", "\n".join(f"- {line}" for line in med_lines)))
        if fus:
            sections.append(("FOLLOW-UP", "\n".join(f"- {f['description']}" + (f" (due {fmt_date(ts(f['due_date'] + 'T00:00:00Z'))})" if f["due_date"] else "") for f in fus)))
        header = (f"{note['type'].upper()}\n{HOSPITAL}\n"
                  f"Patient: {display_name(pid)} | Patient ID: {pid} | MRN: {mrn(pid)} | Encounter: {eid}\n"
                  f"Service: {e['service']} | Author: {CLINICIANS[e['clinician']]} | Date: {fmt_dt(end)}")
        text = header + "\n\n" + "\n\n".join(f"{h}\n{b}" for h, b in sections) + f"\n\n{DISCLAIMER}"
        out["clinical_notes"].append({
            "note_id": note_id, "patient_id": pid, "encounter_id": eid, "note_type": note["type"],
            "author": CLINICIANS[e["clinician"]], "authored_at": iso(end), "title": f"{note['type']} — {e['service']}",
            "note_text": text, "is_synthetic": True,
        })

    # Final medication statuses as of dataset date (courses that ended are completed)
    for m in out["medication_requests"]:
        if m["patient_id"] == pid and m["status"] == "active" and m["end_date"] and ts(m["end_date"]) <= as_of:
            m["status"] = "completed"

    # Portal threads and messages
    for t in p["threads"]:
        tid = f"CN-T{n}-{t['seq']}"
        msgs = t["messages"]
        for i, m in enumerate(msgs, start=1):
            sender = display_name(pid) if m["role"] == "patient" else CLINICIANS[m["sender"]]
            out["portal_messages"].append({
                "message_id": f"CN-MSG{n}-{t['seq']}-{i}", "thread_id": tid, "patient_id": pid,
                "encounter_id": enc_id(pid, t["enc"]), "channel": "patient_portal", "sender_role": m["role"],
                "sender_name": sender, "sent_at": m["ts"], "subject": t["subject"], "message_body": m["body"],
                "is_routing_acknowledgment": bool(m["ack"]), "is_synthetic": True,
            })
        last = msgs[-1]
        status = "awaiting_reply" if last["role"] == "patient" else ("routed" if last["ack"] else "answered")
        first_pt = next(ts(m["ts"]) for m in msgs if m["role"] == "patient")
        first_resp = next((ts(m["ts"]) for m in msgs if m["role"] != "patient"), None)
        out["portal_threads"].append({
            "thread_id": tid, "patient_id": pid, "encounter_id": enc_id(pid, t["enc"]), "subject": t["subject"],
            "category": t["category"], "status": status, "routed_to": t.get("routed_to"),
            "opened_at": msgs[0]["ts"], "last_message_at": last["ts"], "last_sender_role": last["role"],
            "message_count": len(msgs),
            "first_response_minutes": round((first_resp - first_pt).total_seconds() / 60) if first_resp else None,
            "is_synthetic": True,
        })

    # Imaging studies and demonstration reports
    for im in p["imaging"]:
        sid = f"CN-IMG{n}-{im['seq']}"
        rid = f"CN-RAD{n}-{im['seq']}"
        e = encs[im["enc"]]
        eid = enc_id(pid, im["enc"])
        out["imaging_studies"].append({
            "study_id": sid, "patient_id": pid, "encounter_id": eid, "accession_number": f"SYNACC{n}{im['seq']:02d}",
            "ordered_procedure": im["procedure"], "indication": im["indication"], "stored_modality": "OT",
            "sop_class": "Secondary Capture Image Storage", "image_content": "synthetic_test_pattern",
            "study_at": im["ts"], "dicom_path": f"{VOLUME_ROOT}/dicom/{sid}.dcm", "report_id": rid,
            "ordering_clinician": CLINICIANS[e["clinician"]], "is_synthetic": True,
        })
        report = (
            "SYNTHETIC DEMONSTRATION IMAGING REPORT — NOT A RADIOLOGY INTERPRETATION\n"
            f"Patient: {display_name(pid)} | Patient ID: {pid} | Encounter: {eid}\n"
            f"Study: {sid} | Accession: SYNACC{n}{im['seq']:02d} | Date: {fmt_dt(ts(im['ts']))}\n\n"
            f"ORDER\n{im['procedure']}\n\n"
            f"INDICATION (FROM ORDER)\n{im['indication']}\n\n"
            f"ORDERING CLINICIAN\n{CLINICIANS[e['clinician']]}\n\n"
            "STORED OBJECT\nDICOM Secondary Capture (modality OT) containing a geometric test pattern generated for software demonstration.\n\n"
            "FINDINGS\nNone reported. The stored image is not a medical image and was not interpreted.\n\n"
            "IMPRESSION\nNot applicable — demonstration object. No radiological conclusion is documented for this study."
        )
        out["imaging_reports"].append({
            "report_id": rid, "study_id": sid, "patient_id": pid, "encounter_id": eid, "status": "final (demonstration)",
            "report_text": report, "authored_at": im["ts"], "is_synthetic": True,
        })

    # Document index (as a document-management system would export it)
    titles = {"discharge_summary": "Discharge Summary", "lab_report": "Laboratory Report",
              "medrec": "Medication Reconciliation Record", "home_health_scanned": "Home Health Nursing Intake (scanned fax)",
              "referral_scanned": "Gastroenterology Referral (scanned fax)", "misfiled_lab": "Laboratory Report"}
    types = {"discharge_summary": "Discharge summary", "lab_report": "Laboratory report", "consult": "Consultation note",
             "referral": "Referral letter", "operative": "Operative report", "pt_report": "Therapy progress report",
             "medrec": "Medication reconciliation", "home_health_scanned": "Home health intake",
             "referral_scanned": "Referral letter", "misfiled_lab": "Laboratory report"}
    for d in p["documents"]:
        did = f"CN-D{n}-{d['seq']}"
        e = encs[d["enc"]]
        title = titles.get(d["kind"]) or e[{"consult": "consult", "referral": "referral", "operative": "operative", "pt_report": "pt_report"}[d["kind"]]]["title"]
        out["document_index"].append({
            "document_id": did, "patient_id": pid, "encounter_id": enc_id(pid, d["enc"]), "doc_kind": d["kind"],
            "doc_type": types[d["kind"]], "title": title, "author": CLINICIANS[d["author"]], "authored_at": d["ts"],
            "file_name": f"{did}.pdf", "file_path": f"{VOLUME_ROOT}/documents/{did}.pdf",
            "received_via": "Fax (scanned image)" if d["kind"].endswith("_scanned") else "EHR document export",
            "is_synthetic": True,
        })
