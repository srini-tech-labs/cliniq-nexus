"""Render synthetic clinical PDFs from structured v5 records.

Text-layer PDFs are produced with ReportLab. "Scanned" faxes are image-only PDFs produced
with Pillow so that downstream ingestion must detect the missing text layer.
"""
from __future__ import annotations

import io
import random
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from build import DISCLAIMER, display_name, enc_id, fmt_date, fmt_dt, fmt_num, mrn, ts
from catalog import LABS
from scenarios import CLINICIANS, HOSPITAL

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DejaVu", f"{FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))

INK = colors.HexColor("#14213D")
MUTED = colors.HexColor("#5B6475")
ACCENT = colors.HexColor("#0E6E8C")
WARN = colors.HexColor("#A33A22")
RULE = colors.HexColor("#CBD3DE")
FILL = colors.HexColor("#EEF3F8")

S_BODY = ParagraphStyle("body", fontName="DejaVu", fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT)
S_H1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=15, leading=19, textColor=INK, spaceAfter=4)
S_H2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=10, leading=14, textColor=ACCENT, spaceBefore=9, spaceAfter=3)
S_SMALL = ParagraphStyle("small", fontName="DejaVu", fontSize=8, leading=10.5, textColor=MUTED)
S_CELL = ParagraphStyle("cell", fontName="DejaVu", fontSize=8.5, leading=11, textColor=INK)
S_CELLB = ParagraphStyle("cellb", fontName="DejaVu-Bold", fontSize=8.5, leading=11, textColor=INK)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para(text: str, style=S_BODY):
    return Paragraph(esc(text).replace("\n", "<br/>"), style)


def make_canvas(banner: dict):
    """Canvas that stamps header, patient banner and 'Page X of Y' on every page."""

    class BannerCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            w, h = LETTER
            self.setFillColor(FILL)
            self.rect(0, h - 0.95 * inch, w, 0.95 * inch, stroke=0, fill=1)
            self.setFillColor(INK)
            self.setFont("DejaVu-Bold", 11)
            self.drawString(0.6 * inch, h - 0.42 * inch, HOSPITAL)
            self.setFont("DejaVu", 7.5)
            self.setFillColor(WARN)
            self.drawRightString(w - 0.6 * inch, h - 0.42 * inch, "SYNTHETIC DEMONSTRATION DOCUMENT — NOT FOR CLINICAL USE")
            self.setFillColor(INK)
            self.setFont("DejaVu", 8)
            self.drawString(0.6 * inch, h - 0.72 * inch,
                            f"{banner['name']}  |  Patient ID: {banner['patient_id']}  |  MRN: {banner['mrn']}  |  "
                            f"DOB: {banner['dob']}  |  Encounter: {banner['encounter_id']}")
            self.setStrokeColor(RULE)
            self.line(0.6 * inch, 0.62 * inch, w - 0.6 * inch, 0.62 * inch)
            self.setFont("DejaVu", 7.5)
            self.setFillColor(MUTED)
            self.drawString(0.6 * inch, 0.42 * inch, f"Document {banner['document_id']}  |  {banner['title']}")
            self.drawRightString(w - 0.6 * inch, 0.42 * inch, f"Page {self._pageNumber} of {total}")

    return BannerCanvas


def table(rows, widths, header=True, zebra=True):
    data = [[c if not isinstance(c, str) else Paragraph(esc(c), S_CELLB if (header and i == 0) else S_CELL) for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), FILL))
    t.setStyle(TableStyle(style))
    return t


def kv_table(pairs):
    rows = [[Paragraph(esc(k), S_CELLB), Paragraph(esc(v), S_CELL)] for k, v in pairs]
    t = Table(rows, colWidths=[1.6 * inch, 5.3 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def render(path: str, banner: dict, story: list):
    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=1.15 * inch, bottomMargin=0.85 * inch, title=banner["title"],
                            author="ClinIQ Nexus synthetic data generator", subject=DISCLAIMER)
    doc.build(story, canvasmaker=make_canvas(banner))


# --------------------------------------------------------------------------- helpers over records

class PatientView:
    def __init__(self, scenario: dict, recs: dict):
        self.s = scenario
        self.pid = scenario["id"]
        pick = lambda name: [r for r in recs[name] if r["patient_id"] == self.pid]
        self.patient = pick("patients")[0]
        self.encounters = {e["encounter_id"]: e for e in pick("encounters")}
        self.conditions = pick("conditions")
        self.obs = pick("observations")
        self.meds = pick("medication_requests")
        self.followups = pick("follow_up_items")
        self.studies = pick("imaging_studies")

    def enc(self, key):
        return self.encounters[enc_id(self.pid, key)]

    def episode(self, key):
        """Encounter ids of an inpatient episode, including a directly preceding ED visit."""
        e = self.enc(key)
        ids = [e["encounter_id"]]
        for other in self.encounters.values():
            if other["class_code"] == "EMER" and other["end_at"] == e["start_at"]:
                ids.insert(0, other["encounter_id"])
        return ids

    def labs_by_time(self, enc_ids):
        sets = {}
        for o in self.obs:
            if o["category"] == "laboratory" and o["encounter_id"] in enc_ids:
                sets.setdefault(o["effective_at"], {})[o["measure_key"]] = o
        return dict(sorted(sets.items()))


def banner_for(view: PatientView, document_id: str, encounter_id: str, title: str) -> dict:
    b = datetime.fromisoformat(view.patient["birth_date"])
    return {"name": view.patient["display_name"], "patient_id": view.pid, "mrn": view.patient["mrn"],
            "dob": fmt_date(b), "encounter_id": encounter_id, "document_id": document_id, "title": title}


def results_table(view: PatientView, enc_ids):
    sets = view.labs_by_time(enc_ids)
    if not sets:
        return None
    times = list(sets)
    keys = []
    for s in sets.values():
        for k in s:
            if k not in keys:
                keys.append(k)
    header = ["Test"] + [fmt_dt(ts(t)).replace(" UTC", "") for t in times] + ["Units", "Reference"]
    rows = [header]
    for k in keys:
        spec = LABS[k]
        any_obs = next(s[k] for s in sets.values() if k in s)
        lo, hi = any_obs["ref_low"], any_obs["ref_high"]
        ref = f"{fmt_num(lo)}–{fmt_num(hi)}" if lo is not None and hi is not None else (f"≥ {fmt_num(lo)}" if lo is not None else (f"≤ {fmt_num(hi)}" if hi is not None else "—"))
        cells = []
        for t in times:
            o = sets[t].get(k)
            cells.append("" if not o else fmt_num(o["value"]) + ("" if o["interpretation"] == "N" else f" {o['interpretation']}"))
        rows.append([spec["name"]] + cells + [spec["display_unit"], ref])
    n = len(times)
    value_w = min(1.0, 3.35 / n) * inch
    return table(rows, [1.75 * inch] + [value_w] * n + [1.0 * inch, 0.95 * inch])


def meds_at(view: PatientView, when: str):
    t = ts(when)
    active = []
    for m in view.meds:
        if m["category"] == "inpatient":
            continue
        authored = ts(m["authored_on"])
        ended = ts(m["end_date"]) if m["end_date"] else None
        if authored <= t and (ended is None or ended > t):
            active.append(m)
    return active


# --------------------------------------------------------------------------- document kinds

def discharge_summary(view, doc, path):
    e = view.encounters[doc["encounter_id"]]
    key = e["encounter_id"].split("-")[-1]
    episode = view.episode(key)
    scen_e = next(x for x in view.s["encounters"] if x["key"] == key)
    start, end = ts(e["start_at"]), ts(e["end_at"])
    if len(episode) > 1:
        start = ts(view.encounters[episode[0]]["start_at"])
    story = [para("Discharge Summary", S_H1),
             kv_table([("Admission", fmt_dt(start)), ("Discharge", fmt_dt(end)),
                       ("Length of stay", f"{(end.date() - start.date()).days} days"),
                       ("Service", e["service"]), ("Attending", e["attending"]), ("Disposition", e["disposition"])])]
    story += [para("Diagnoses", S_H2),
              para("\n".join(f"{c['code']} — {c['display']}" for c in view.conditions if c["encounter_id"] == e["encounter_id"]))]
    story += [para("Reason for admission", S_H2), para(e["reason"])]
    story += [para("Hospital course", S_H2), para(scen_e["hospital_course"])]
    vit = [o for o in view.obs if o["encounter_id"] in episode and o["category"] == "vital-signs"]
    if vit:
        first_t, last_t = min(o["effective_at"] for o in vit), max(o["effective_at"] for o in vit)
        def vset(tt):
            vals = {o["measure_key"]: o for o in vit if o["effective_at"] == tt}
            parts = []
            for k, label, unit in [("temp", "Temp", " °C"), ("hr", "HR", " bpm"), ("rr", "RR", "/min"), ("spo2", "SpO2", "%"), ("wt", "Weight", " kg"), ("pain", "Pain", "/10")]:
                if k in vals:
                    parts.append(f"{label} {fmt_num(vals[k]['value'])}{unit}")
            if "sbp" in vals:
                parts.append(f"BP {fmt_num(vals['sbp']['value'])}/{fmt_num(vals['dbp']['value'])} mmHg")
            return ", ".join(parts)
        story += [para("Vital signs", S_H2),
                  para(f"First recorded ({fmt_dt(ts(first_t))}): {vset(first_t)}\nAt discharge ({fmt_dt(ts(last_t))}): {vset(last_t)}")]
    rt = results_table(view, episode)
    if rt is not None:
        story.append(KeepTogether([para("Key laboratory results", S_H2), rt,
                                   para("Flags: H = above reference range, L = below reference range.", S_SMALL)]))
    studies = [s for s in view.studies if s["encounter_id"] in episode]
    if studies:
        story += [para("Imaging during this episode", S_H2),
                  para("\n".join(f"{s['ordered_procedure']} on {fmt_date(ts(s['study_at']))} (study {s['study_id']}). "
                                 "Stored object is a synthetic test pattern; no imaging interpretation is documented." for s in studies))]
    # Discharge medications with change labels relative to the episode
    window_start = start
    active = meds_at(view, e["end_at"])
    replaced = {m["prior_request_id"] for m in view.meds if m["prior_request_id"]}
    rows = [["Medication", "Dose", "Route", "Frequency", "Status at discharge"]]
    for m in active:
        authored = ts(m["authored_on"])
        if m["action"] == "changed" and authored >= window_start:
            prior = next(x for x in view.meds if x["medication_request_id"] == m["prior_request_id"])
            label = f"CHANGED (was {prior['dose']})"
        elif m["action"] == "started" and authored >= window_start:
            label = "NEW" + (f" — {(ts(m['end_date']).date() - authored.date()).days}-day course" if m["end_date"] else "")
        else:
            label = "CONTINUED"
        rows.append([m["medication"], m["dose"], m["route"], m["frequency"], label])
    for m in view.meds:
        if (m["status"] == "stopped" and m["medication_request_id"] not in replaced and m["category"] != "inpatient"
                and m["end_date"] and window_start <= ts(m["end_date"]) <= end):
            replacement = next((x for x in active if x["medication"] == m["medication"]), None)
            note = f"STOPPED — {m['stop_reason']}" if not replacement else f"STOPPED ({m['dose']} replaced by {replacement['dose']})"
            rows.append([m["medication"], m["dose"], m["route"], m["frequency"], note])
    story.append(KeepTogether([para("Discharge medications", S_H2),
                               table(rows, [1.7 * inch, 1.2 * inch, 0.85 * inch, 1.35 * inch, 1.8 * inch])]))
    fus = [f for f in view.followups if f["encounter_id"] == e["encounter_id"]]
    if fus:
        story += [para("Follow-up", S_H2),
                  para("\n".join(f"• {f['description']}" + (f" — by {fmt_date(ts(f['due_date'] + 'T00:00:00Z'))}" if f["due_date"] else "") for f in fus))]
    story += [Spacer(1, 10), para(f"Electronically signed: {e['attending']} — {fmt_dt(ts(doc['authored_at']))}", S_SMALL)]
    render(path, banner_for(view, doc["document_id"], e["encounter_id"], doc["title"]), story)


def lab_report(view, doc, path, lab_encs=None, banner_enc=None, doc_id_override=None):
    keys = lab_encs or [doc["encounter_id"].split("-")[-1]]
    enc_ids = [enc_id(view.pid, k) for k in keys]
    e = view.encounters[banner_enc or doc["encounter_id"]]
    story = [para("Laboratory Report — Cumulative Results", S_H1),
             kv_table([("Ordering clinician", e["attending"]), ("Report date", fmt_dt(ts(doc["authored_at"]))),
                       ("Performing laboratory", f"{HOSPITAL} Clinical Laboratory"),
                       ("Encounters included", ", ".join(enc_ids))]),
             para("Results", S_H2), results_table(view, enc_ids),
             para("Flags: H = above reference range, L = below reference range. Reference ranges are typical adult ranges "
                  "used for this synthetic demonstration.", S_SMALL),
             Spacer(1, 10), para(f"Report released {fmt_dt(ts(doc['authored_at']))}. {DISCLAIMER}", S_SMALL)]
    render(path, banner_for(view, doc_id_override or doc["document_id"], e["encounter_id"], doc["title"]), story)


def sectioned(view, doc, path, spec_key):
    e = view.encounters[doc["encounter_id"]]
    key = e["encounter_id"].split("-")[-1]
    spec = next(x for x in view.s["encounters"] if x["key"] == key)[spec_key]
    story = [para(spec["title"], S_H1)]
    pairs = [("Date", fmt_dt(ts(doc["authored_at"]))), ("Author", doc["author"]), ("Service", e["service"])]
    if spec.get("to"):
        pairs.insert(0, ("Referred to", spec["to"]))
        pairs.insert(1, ("Referred by", doc["author"]))
    story.append(kv_table(pairs))
    vit = [o for o in view.obs if o["encounter_id"] == e["encounter_id"] and o["category"] == "vital-signs"]
    for heading, body in spec["sections"]:
        story += [para(heading, S_H2), para(body)]
    if spec_key == "consult" and vit:
        latest = {o["measure_key"]: o for o in vit}
        parts = [f"{o['name']} {fmt_num(o['value'])} {o['display_unit']}" for k, o in latest.items()]
        story += [para("Vital signs at visit", S_H2), para("; ".join(parts))]
    story += [Spacer(1, 10), para(f"Electronically signed: {doc['author']} — {fmt_dt(ts(doc['authored_at']))}", S_SMALL)]
    render(path, banner_for(view, doc["document_id"], e["encounter_id"], doc["title"]), story)


def medrec(view, doc, path):
    e = view.encounters[doc["encounter_id"]]
    key = e["encounter_id"].split("-")[-1]
    spec = next(x for x in view.s["encounters"] if x["key"] == key)["medrec"]
    rows = [["Medication", "Prescribed regimen", "Source list", "Patient report", "Reconciled action"]]
    for m in meds_at(view, e["start_at"]):
        rows.append([m["medication"], f"{m['dose']} {m['frequency']}", "Discharge list" if m["category"] in ("discharge",) else "Home list (continued)",
                     "Taking as prescribed", "Continue"])
    for m in view.meds:
        if m["status"] == "stopped" and m["medication"] in spec["discrepancy"]:
            rows.append([m["medication"], f"{m['dose']} {m['frequency']}", f"Stopped {fmt_date(ts(m['end_date']))}",
                         "Still taking", "Stop — patient instructed"])
    story = [para(spec["title"], S_H1),
             kv_table([("Date", fmt_dt(ts(doc["authored_at"]))), ("Reconciled by", doc["author"]),
                       ("Reason", e["reason"]), ("Sources compared", "Hospital discharge medication list; patient-provided bottles; patient interview")]),
             para("Reconciled medication list", S_H2),
             table(rows, [1.5 * inch, 1.6 * inch, 1.3 * inch, 1.15 * inch, 1.35 * inch]),
             para("Discrepancy", S_H2), para(spec["discrepancy"]),
             Spacer(1, 10), para(f"Electronically signed: {doc['author']} — {fmt_dt(ts(doc['authored_at']))}", S_SMALL)]
    render(path, banner_for(view, doc["document_id"], e["encounter_id"], doc["title"]), story)


# --------------------------------------------------------------------------- scanned (image-only)

def scanned_pdf(path: str, pages: list[list[str]], seed: int):
    rnd = random.Random(seed)
    mono = ImageFont.truetype(f"{FONT_DIR}/DejaVuSansMono.ttf", 30)
    bold = ImageFont.truetype(f"{FONT_DIR}/DejaVuSansMono-Bold.ttf", 34)
    images = []
    for lines in pages:
        img = Image.new("L", (1700, 2200), 250)
        d = ImageDraw.Draw(img)
        y = 120
        for i, line in enumerate(lines):
            d.text((130, y), line, fill=rnd.randint(20, 60), font=bold if line.isupper() and line else mono)
            y += 54 if line else 30
        noise = Image.effect_noise((1700, 2200), 18).point(lambda v: 255 if v > 110 else 0)
        img = Image.composite(img, Image.new("L", img.size, 235), noise.convert("L").point(lambda v: 255 if v else 0))
        img = img.rotate(rnd.uniform(-0.8, 0.8), fillcolor=245, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.7))
        images.append(img.convert("RGB"))
    images[0].save(path, "PDF", resolution=200.0, save_all=True, append_images=images[1:])


def home_health_scanned(view, doc, path):
    p = view.patient
    pages = [[
        f"FAX  09/05/2026 15:02   Nexus Home Health Services (fictional)   P.1/2",
        "", "HOME HEALTH NURSING INTAKE", "SYNTHETIC DEMONSTRATION DOCUMENT - NOT FOR CLINICAL USE", "",
        f"Patient: {p['display_name']}", f"Patient ID: {view.pid}    MRN: {p['mrn']}",
        f"Referring encounter: {doc['encounter_id']} (discharged 9/3/2026)", "Visit date: 9/5/2026", "",
        "Weight (home scale): 80.4 kg", "BP 120/72   HR 76   SpO2 96%", "",
        "Medications reviewed with patient:", "  furosemide 40 mg daily", "  spironolactone 12.5 mg daily",
        "  metoprolol succinate 25 mg daily", "  lisinopril 10 mg daily", "  atorvastatin 40 mg nightly",
        "  Old furosemide 20 mg bottle set aside by patient.", "",
        "Education: daily weights, low-sodium diet, symptom log.", "Next nursing visit: 9/9/2026.",
    ], [
        f"FAX  09/05/2026 15:02   Nexus Home Health Services (fictional)   P.2/2", "",
        "PLAN OF CARE", "", "Skilled nursing 2x/week x 3 weeks.", "Report weight gain > 1 kg/day or 2 kg/week to PCP.",
        "", f"Patient ID: {view.pid}", "", "Signed: L. Ortiz, RN (fictional)",
    ]]
    scanned_pdf(path, pages, seed=int(view.pid[-3:]) * 7)


def referral_scanned(view, doc, path):
    p = view.patient
    pages = [[
        f"FAX  07/15/2026 10:04   Nexus General Primary Care (fictional)   P.1/1",
        "", "REFERRAL - GASTROENTEROLOGY", "SYNTHETIC DEMONSTRATION DOCUMENT - NOT FOR CLINICAL USE", "",
        f"Patient: {p['display_name']}", f"Patient ID: {view.pid}    MRN: {p['mrn']}", f"Encounter: {doc['encounter_id']}", "",
        "Reason: iron-deficiency anemia, source evaluation requested.", "Hemoglobin 9.6 g/dL, MCV 74 fL, ferritin 6 ng/mL (7/14/2026).",
        "Started ferrous sulfate 325 mg daily.", "", "Priority: routine", "",
        f"Referring clinician: {CLINICIANS['pcp']}", "Please contact patient directly to schedule.",
    ]]
    scanned_pdf(path, pages, seed=int(view.pid[-3:]) * 11)


def render_documents(scenarios: list, recs: dict, out_dir: str) -> list[dict]:
    """Render every indexed document. Returns render log entries."""
    log = []
    views = {s["id"]: PatientView(s, recs) for s in scenarios}
    for doc in recs["document_index"]:
        view = views[doc["patient_id"]]
        spec = next(d for d in view.s["documents"] if f"CN-D{view.pid[-3:]}-{d['seq']}" == doc["document_id"])
        path = f"{out_dir}/{doc['file_name']}"
        kind = doc["doc_kind"]
        if kind == "discharge_summary":
            discharge_summary(view, doc, path)
        elif kind == "lab_report":
            lab_report(view, doc, path, lab_encs=spec.get("lab_encs"))
        elif kind in ("consult", "referral", "operative", "pt_report"):
            sectioned(view, doc, path, {"consult": "consult", "referral": "referral", "operative": "operative", "pt_report": "pt_report"}[kind])
        elif kind == "medrec":
            medrec(view, doc, path)
        elif kind == "home_health_scanned":
            home_health_scanned(view, doc, path)
        elif kind == "referral_scanned":
            referral_scanned(view, doc, path)
        elif kind == "misfiled_lab":
            # Content (banner and results) belong to another patient; the index entry does not.
            other = views[spec["content_patient"]]
            other_doc = dict(doc, encounter_id=enc_id(other.pid, spec["content_enc"]))
            lab_report(other, other_doc, path, lab_encs=["01", "02", "04"], doc_id_override=doc["document_id"])
        log.append({"document_id": doc["document_id"], "path": path, "kind": kind})
    return log
