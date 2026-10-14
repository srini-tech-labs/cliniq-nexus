"""Deterministic answers for structured questions, built directly from patient records.

No language model is involved: every claim is produced from rows and cites those rows.
"""
from __future__ import annotations

import re
from collections import defaultdict

from ..clinical import day, num, parse, short


class Builder:
    def __init__(self):
        self.claims: list[dict] = []
        self.sources: list[dict] = []
        self._index: dict[tuple, str] = {}

    def src(self, kind: str, rid: str, label: str, excerpt: str, date: str | None = None, page: int | None = None,
            document_id: str | None = None, encounter_id: str | None = None) -> str:
        key = (kind, rid, page)
        if key not in self._index:
            sid = f"S{len(self.sources) + 1}"
            self._index[key] = sid
            self.sources.append({"sid": sid, "type": kind, "id": rid, "label": label, "excerpt": excerpt, "date": date,
                                 "page": page, "document_id": document_id, "encounter_id": encounter_id})
        return self._index[key]

    def documented(self, text: str, sids: list[str]):
        self.claims.append({"kind": "documented", "text": text, "citations": sids})

    def missing(self, text: str):
        self.claims.append({"kind": "not_documented", "text": text, "citations": []})


def med_src(b: Builder, m: dict) -> str:
    excerpt = (f"{m['medication']} {m['dose']} {m['route']} {m['frequency']}. Status: {m['status']}. "
               f"Category: {m['category']}. Ordered {day(m['authored_on'])}" + (f"; ends/ended {day(m['end_date'])}" if m["end_date"] else "")
               + f". Reason: {m['reason']}." + (f" Stop reason: {m['stop_reason']}." if m["stop_reason"] else ""))
    return b.src("medication", m["medication_request_id"], f"Medication order · {m['medication']} · {day(m['authored_on'])}",
                 excerpt, m["authored_on"], encounter_id=m["encounter_id"])


def obs_src(b: Builder, o: dict, label: str | None = None) -> str:
    flag = f" ({o['interpretation']})" if o.get("interpretation") not in (None, "N") else ""
    excerpt = f"{o['name']}: {num(o['value'])} {o['display_unit']}{flag} recorded {day(o['effective_at'])} (encounter {o['encounter_id']})."
    return b.src("observation", o["observation_id"], label or f"{o['name']} · {day(o['effective_at'])}", excerpt,
                 o["effective_at"], encounter_id=o["encounter_id"])


def enc_src(b: Builder, e: dict) -> str:
    excerpt = (f"{e['encounter_type']} ({e['class_display']}), {e['service']}, {day(e['start_at'])}. Reason: {e['reason']}. "
               f"Disposition: {e['disposition']}. Attending: {e['attending']}.")
    return b.src("encounter", e["encounter_id"], f"{e['encounter_type']} · {day(e['start_at'])}", excerpt, e["start_at"], encounter_id=e["encounter_id"])


def note_src(b: Builder, n: dict) -> str:
    return b.src("clinical_note", n["note_id"], f"{n['note_type']} · {day(n['authored_at'])}", n["note_text"], n["authored_at"], encounter_id=n["encounter_id"])


# --------------------------------------------------------------------------- intents

def medications(bundle: dict, question: str) -> Builder:
    b = Builder()
    meds = bundle["medications"]
    if not meds:
        b.missing("No medication orders are documented in the available records.")
        return b
    active = [m for m in meds if m["status"] == "active"]
    replaced = {m["prior_request_id"] for m in meds if m["prior_request_id"]}
    if active:
        for m in active:
            since = "home medication documented" if m["category"] == "home" else f"since {day(m['authored_on'])}"
            b.documented(f"Active: {m['medication']} {m['dose']} {m['route']} {m['frequency']} ({since}).", [med_src(b, m)])
    changes = []
    for m in meds:
        if m["action"] == "changed":
            prior = next((p for p in meds if p["medication_request_id"] == m["prior_request_id"]), None)
            changes.append((m["authored_on"], f"{m['medication']} changed from {prior['dose'] if prior else 'prior dose'} to {m['dose']} on {day(m['authored_on'])} ({m['reason']}).",
                            [med_src(b, m)] + ([med_src(b, prior)] if prior else [])))
        elif m["status"] == "stopped" and m["medication_request_id"] not in replaced and m["category"] != "inpatient":
            changes.append((m["end_date"], f"{m['medication']} {m['dose']} stopped on {day(m['end_date'])}: {m['stop_reason']}.", [med_src(b, m)]))
        elif m["status"] == "completed" and m["category"] != "inpatient":
            changes.append((m["end_date"], f"{m['medication']} {m['dose']} course completed {day(m['end_date'])}.", [med_src(b, m)]))
    for _, text, sids in sorted(changes, key=lambda c: c[0] or ""):
        b.documented(text, sids)
    inpatient = [m for m in meds if m["category"] == "inpatient"]
    if inpatient:
        names = ", ".join(sorted({m["medication"] for m in inpatient}))
        b.documented(f"Inpatient-only orders (not continued after discharge): {names}.", [med_src(b, m) for m in inpatient])
    b.missing("Medication adherence and administration records are not available in this dataset beyond what notes and messages state.")
    return b


VITAL_ORDER = ["sbp", "hr", "spo2", "temp", "rr", "wt", "pain"]


def vitals(bundle: dict, question: str) -> Builder:
    b = Builder()
    q = question.lower()
    series = defaultdict(list)
    for o in bundle["observations"]:
        if o["category"] == "vital-signs":
            series[o["measure_key"]].append(o)
    wanted = [k for k, pat in [("sbp", r"blood pressure|\bbp\b|systolic|diastolic"), ("hr", r"heart rate|pulse"),
                               ("spo2", r"oxygen|spo2|saturation"), ("temp", r"temperature|fever"), ("rr", r"respiratory"),
                               ("wt", r"weight"), ("pain", r"pain")] if re.search(pat, q)] or [k for k in VITAL_ORDER if k in series]
    for key in wanted:
        s = series.get(key)
        if not s:
            b.missing(f"No {key_name(key)} measurements are documented.")
            continue
        first, last = s[0], s[-1]
        if key == "sbp":
            dia = {o["panel_id"]: o for o in series.get("dbp", [])}
            fd, ld = dia.get(first["panel_id"]), dia.get(last["panel_id"])
            text = (f"Blood pressure {num(first['value'])}/{num(fd['value']) if fd else '?'} mmHg on {day(first['effective_at'])}; "
                    f"most recent {num(last['value'])}/{num(ld['value']) if ld else '?'} mmHg on {day(last['effective_at'])} ({len(s)} readings).")
            sids = [obs_src(b, first), obs_src(b, last)] + [obs_src(b, x) for x in (fd, ld) if x]
        elif len(s) == 1:
            text = f"{first['name']} {num(first['value'])} {first['display_unit']} on {day(first['effective_at'])} (single measurement)."
            sids = [obs_src(b, first)]
        else:
            lo, hi = min(s, key=lambda o: o["value"]), max(s, key=lambda o: o["value"])
            text = (f"{first['name']} {num(first['value'])} {first['display_unit']} on {day(first['effective_at'])}; most recent "
                    f"{num(last['value'])} {last['display_unit']} on {day(last['effective_at'])} (range {num(lo['value'])}–{num(hi['value'])} across {len(s)} measurements).")
            sids = [obs_src(b, first), obs_src(b, last)]
        b.documented(text, sids)
    b.missing("Home or continuous monitoring data are not recorded as structured observations; values reported in portal messages are not included here.")
    return b


def key_name(key: str) -> str:
    return {"sbp": "blood pressure", "hr": "heart rate", "spo2": "oxygen saturation", "temp": "temperature",
            "rr": "respiratory rate", "wt": "body weight", "pain": "pain score"}[key]


LAB_WORDS = {"a1c": r"a1c", "ldl": r"\bldl", "hdl": r"\bhdl", "tc": r"cholesterol", "tg": r"triglycer", "cr": r"creatinine",
             "egfr": r"egfr|kidney", "k": r"potassium", "na": r"sodium", "hgb": r"hemoglobin|anemia", "bnp": r"\bbnp",
             "ferritin": r"ferritin|iron", "glu": r"glucose|sugar", "wbc": r"\bwbc|white blood", "crp": r"\bcrp|c-reactive",
             "alt": r"\balt\b|liver", "tsh": r"\btsh|thyroid", "uacr": r"albumin|uacr", "mcv": r"\bmcv", "fev1": r"fev1|spirometry"}


def labs(bundle: dict, question: str) -> Builder:
    b = Builder()
    q = question.lower()
    series = defaultdict(list)
    for o in bundle["observations"]:
        if o["category"] == "laboratory":
            series[o["measure_key"]].append(o)
    if not series:
        b.missing("No laboratory results are documented in the available records.")
        return b
    wanted = [k for k, pat in LAB_WORDS.items() if re.search(pat, q)]
    if not wanted:
        wanted = sorted(series, key=lambda k: series[k][-1]["effective_at"], reverse=True)
    for key in wanted:
        s = series.get(key)
        if not s:
            b.missing(f"No {key.upper() if len(key) < 4 else key} result is documented.")
            continue
        last = s[-1]
        flag = {"H": " (above reference range)", "L": " (below reference range)"}.get(last["interpretation"], "")
        if len(s) == 1:
            b.documented(f"{last['name']} {num(last['value'])} {last['display_unit']}{flag} on {day(last['effective_at'])}.", [obs_src(b, last)])
        else:
            path = " → ".join(f"{num(o['value'])} ({short(o['effective_at'])})" for o in s)
            b.documented(f"{last['name']} ({last['display_unit']}): {path}; latest{flag or ' within reference range'}.",
                         [obs_src(b, o) for o in s])
    return b


def messages(bundle: dict, question: str) -> Builder:
    b = Builder()
    threads = bundle["threads"]
    if not threads:
        b.missing("No patient portal messages are documented.")
        return b
    now = parse(bundle["as_of"])
    order = {"awaiting_reply": 0, "routed": 1, "answered": 2}
    for t in sorted(threads, key=lambda t: (order[t["status"]], t["last_message_at"])):
        pmsgs = [m for m in t["messages"] if m["sender_role"] == "patient"]
        last_pt = pmsgs[-1]
        sid = b.src("portal_message", last_pt["message_id"], f"Portal message · Patient · {day(last_pt['sent_at'])}",
                    f"Subject: {t['subject']}. {last_pt['message_body']}", last_pt["sent_at"], encounter_id=t["encounter_id"])
        if t["status"] == "awaiting_reply":
            waited = (now - parse(t["last_message_at"])).days
            b.documented(f"Awaiting reply ({waited} day{'s' if waited != 1 else ''}): on {day(last_pt['sent_at'])} the patient wrote “{last_pt['message_body']}” No care-team reply is recorded.", [sid])
        else:
            reply = [m for m in t["messages"] if m["sender_role"] != "patient"][-1]
            rsid = b.src("portal_message", reply["message_id"], f"Portal message · {reply['sender_name'].split(' — ')[0]} · {day(reply['sent_at'])}",
                         f"Subject: {t['subject']}. {reply['message_body']}", reply["sent_at"], encounter_id=t["encounter_id"])
            status = (f"Routed to {t['routed_to']}; no completion recorded" if t["status"] == "routed" else "Answered")
            b.documented(f"{status}: “{t['subject']}” ({day(last_pt['sent_at'])}) — patient asked “{last_pt['message_body']}”", [sid, rsid])
    return b


def follow_up(bundle: dict, question: str) -> Builder:
    b = Builder()
    items = bundle["follow_ups"]
    if not items:
        b.missing("No follow-up items are documented.")
        return b
    notes = {n["note_id"]: n for n in bundle["notes"]}
    encs = {e["encounter_id"]: e for e in bundle["encounters"]}
    now = parse(bundle["as_of"])
    order = {"open": 0, "scheduled": 1, "completed": 2}
    for f in sorted(items, key=lambda f: (order[f["status"]], f["due_date"] or "9999")):
        sids = [note_src(b, notes[f["source_note_id"]])]
        due = f" (due {day(f['due_date'])})" if f["due_date"] else ""
        if f["status"] == "completed":
            if f["resolved_encounter_id"]:
                sids.append(enc_src(b, encs[f["resolved_encounter_id"]]))
                b.documented(f"Completed: {f['description']}{due} — documented at the {day(encs[f['resolved_encounter_id']]['start_at'])} encounter.", sids)
            else:
                b.documented(f"Completed: {f['description']}{due}.", sids)
        elif f["status"] == "scheduled":
            b.documented(f"Scheduled: {f['description']}{due}.", sids)
        else:
            overdue = f["due_date"] and parse(f["due_date"]) < now
            b.documented(f"{'Past due' if overdue else 'Open'}: {f['description']}{due}; no completion is documented.", sids)
    return b


def imaging(bundle: dict, question: str) -> Builder:
    b = Builder()
    studies = bundle["imaging"]
    if not studies:
        b.missing("No imaging studies are documented for this patient.")
        return b
    for s in studies:
        r = s.get("report")
        sid = b.src("imaging_report", r["report_id"], f"Imaging report (demonstration) · {day(s['study_at'])}", r["report_text"], s["study_at"],
                    encounter_id=s["encounter_id"]) if r else None
        b.documented(f"{s['ordered_procedure']} on {day(s['study_at'])} (indication: {s['indication']}); the stored DICOM object is a synthetic "
                     "secondary-capture test pattern.", [sid] if sid else [])
        if r:
            b.documented("The linked report states: “Findings: None reported. The stored image is not a medical image and was not interpreted.”", [sid])
    b.missing("No radiological interpretation exists for these studies, and ClinIQ Nexus does not interpret images.")
    return b


def encounters(bundle: dict, question: str) -> Builder:
    b = Builder()
    for e in bundle["encounters"]:
        b.documented(f"{day(e['start_at'])}: {e['encounter_type']} ({e['service']}) — {e['reason']}. {e['disposition']}.", [enc_src(b, e)])
    return b


def documents(bundle: dict, question: str) -> Builder:
    b = Builder()
    if not bundle["documents"]:
        b.missing("No PDF documents are filed for this patient.")
        return b
    for d in bundle["documents"]:
        sid = b.src("document", d["document_id"], f"{d['title']} · {day(d['authored_at'])}",
                    f"{d['doc_type']}, {d['page_count']} page(s), authored by {d['author']}. Identity check: {d['identity_status']}.",
                    d["authored_at"], page=1, document_id=d["document_id"], encounter_id=d["encounter_id"])
        state = "text extracted and searchable" if d["has_text_layer"] else "scanned image with no text layer; not searchable (OCR not performed)"
        b.documented(f"{d['title']} ({day(d['authored_at'])}, {d['page_count']} page{'s' if d['page_count'] > 1 else ''}) — {state}.", [sid])
    return b


def gaps(bundle: dict, question: str) -> Builder:
    b = Builder()
    for d in bundle["documents"]:
        if not d["has_text_layer"]:
            sid = b.src("document", d["document_id"], f"{d['title']} · {day(d['authored_at'])}", "Scanned image PDF; no text layer.",
                        d["authored_at"], page=1, document_id=d["document_id"], encounter_id=d["encounter_id"])
            b.documented(f"The content of “{d['title']}” cannot be searched or cited by the assistant: it is a scanned image and OCR was not performed.", [sid])
    for s in bundle["imaging"]:
        if s.get("report"):
            sid = b.src("imaging_report", s["report"]["report_id"], f"Imaging report (demonstration) · {day(s['study_at'])}",
                        s["report"]["report_text"], s["study_at"], encounter_id=s["encounter_id"])
            b.documented(f"No imaging interpretation exists for the {s['ordered_procedure'].lower()} on {day(s['study_at'])}; the stored object is a synthetic test pattern.", [sid])
    for t in bundle["threads"]:
        if t["status"] in ("awaiting_reply", "routed"):
            m = [x for x in t["messages"] if x["sender_role"] == "patient"][-1]
            sid = b.src("portal_message", m["message_id"], f"Portal message · Patient · {day(m['sent_at'])}", m["message_body"], m["sent_at"], encounter_id=t["encounter_id"])
            b.documented(f"The outcome of the portal request “{t['subject']}” is not documented ({'no reply recorded' if t['status'] == 'awaiting_reply' else 'routed, no completion recorded'}).", [sid])
    notes = {n["note_id"]: n for n in bundle["notes"]}
    for f in bundle["follow_ups"]:
        if f["status"] == "open":
            b.documented(f"Completion of “{f['description']}” is not documented.", [note_src(b, notes[f["source_note_id"]])])
    b.missing("Records from outside Nexus General Hospital (fictional), pharmacy fill history and medication adherence are not part of this dataset.")
    return b


HANDLERS = {"medications": medications, "vitals": vitals, "labs": labs, "messages": messages, "follow_up": follow_up,
            "imaging": imaging, "encounters": encounters, "documents": documents, "gaps": gaps}


def answer(intent: str, bundle: dict, question: str) -> Builder:
    return HANDLERS[intent](bundle, question)
