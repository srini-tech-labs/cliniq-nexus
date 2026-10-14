"""Question routing: scope and safety policy first, then deterministic structured intents."""
from __future__ import annotations

import re

from .retrieval import normalize

OTHER_PATIENT = re.compile(r"\bCN-P\d{3}\b", re.I)
SCOPE = re.compile(r"\b(other|another|all|every|different)\s+(patients?|people|members)\b|\bcompare (him|her|them|this patient) (with|to)\b|\bpopulation\b", re.I)
ADVICE = re.compile(
    r"\bshould (i|we|he|she|they|the patient|this patient)\b|\b(do|would|can|could) you (recommend|suggest|advise)\b|\byour (recommendation|advice|opinion)\b|\bwhat (dose|treatment|medication) should\b"
    r"|\b(increase|decrease|adjust|titrate|change|stop|start)\b.{0,25}\b(dose|dosing|medication|insulin|glargine|drug)\b.{0,12}\?"
    r"|\bis it safe\b|\bprognosis\b|\bwill (he|she|they|the patient) (recover|die|improve|need)\b|\bwhat is wrong\b"
    r"|\bdiagnos(e|is) (this|the|her|him|them)\b|\b(best|next) (treatment|step|therapy)\b|\btreatment (plan|options?) (for|should)\b"
    r"|\bcan (i|he|she|they|the patient) (take|stop|skip|double)\b", re.I)
IMAGE_READ = re.compile(
    r"\b(what does|what do|describe|interpret|read|analy[sz]e|look at)\b.{0,30}\b(image|images|x-?ray|radiograph|scan|pixels?|dicom|picture|film)\b"
    r"|\b(image|x-?ray|radiograph|scan|dicom)\b.{0,20}\b(show|shows|showing|reveal|demonstrate|findings?)\b"
    r"|\bany (fracture|pneumonia|opacity|effusion|infiltrate)s? on\b", re.I)

INTENTS = [
    ("gaps", re.compile(r"\b(cannot|can't|can not|unable to) be (established|determined|known)|\bwhat (is|information is) (missing|unknown|not documented)|\bgaps?\b|\blimitations?\b", re.I)),
    ("messages", re.compile(r"\b(portal|message|messages|messaged|unanswered|awaiting|reply|replied|inbox|asked|questions? did)\b", re.I)),
    ("follow_up", re.compile(r"\bfollow[- ]?ups?\b|\boutstanding\b|\bpending\b|\breferrals?\b|\bscheduled\b|\bnext steps?\b", re.I)),
    ("imaging", re.compile(r"\b(imaging|images?|x-?rays?|radiographs?|scans?|stud(y|ies)|echocardiogram|echo|ultrasound|dicom)\b", re.I)),
    ("medications", re.compile(r"\b(medications?|medicines?|meds|drugs?|prescri\w*|taking|regimen|doses?)\b", re.I)),
    ("vitals", re.compile(r"\b(vitals?|vital signs?|blood pressure|bp|heart rate|pulse|oxygen|spo2|saturation|temperature|fever|weight|respiratory rate|pain score)\b", re.I)),
    ("labs", re.compile(r"\b(labs?|laborator\w*|results?|a1c|hba1c|ldl|hdl|cholesterol|triglycerides?|creatinine|egfr|potassium|sodium|hemoglobin|bnp|ferritin|glucose|wbc|white blood|crp|alt|tsh|albumin|uacr|mcv|fev1)\b", re.I)),
    ("encounters", re.compile(r"\b(visits?|encounters?|admissions?|hospitali[sz]ations?|ed visits?|appointments?)\b", re.I)),
    ("documents", re.compile(r"\b(documents?|pdfs?|files?)\b", re.I)),
]
LISTY = re.compile(r"^\s*(what|which|list|show|how many|are there|is there|when|how (has|have|did|is|are))\b|\b(trend|changed?|over time|latest|current|recorded|available|status)\b", re.I)
NARRATIVE = re.compile(r"\b(why|reason|brought|explain|summari[sz]e|summary|what happened|course|concerns?|instructions?|plan|say about|said|described?|mention)\b", re.I)


def route(question: str, patient_id: str) -> tuple[str, str | None]:
    """Return (route, detail). Routes: policy_scope, policy_advice, policy_imaging, structured, rag."""
    q = normalize(question)
    others = {m.upper() for m in OTHER_PATIENT.findall(question)} - {patient_id}
    if others or SCOPE.search(q):
        return "policy_scope", None
    if IMAGE_READ.search(q):
        return "policy_imaging", None
    if ADVICE.search(q):
        return "policy_advice", None
    for name, pattern in INTENTS:
        if pattern.search(q):
            if name in ("gaps",):
                return "structured", name
            narrative = NARRATIVE.search(q)
            if name in ("follow_up",) and not re.search(r"\b(why|explain|discharge summary|say about)\b", q):
                return "structured", name
            if name == "messages" and not re.search(r"\b(why|explain)\b", q):
                return "structured", name
            if name == "imaging" and not narrative:
                return "structured", name
            if LISTY.search(q) and not narrative:
                return "structured", name
            return "rag", name
    return "rag", None
