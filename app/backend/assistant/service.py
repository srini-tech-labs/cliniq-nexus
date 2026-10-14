"""Assistant orchestration: route → (policy | deterministic | retrieve → generate → validate) → answer."""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import Counter

from ..clinical import day, patient_bundle
from ..config import settings
from ..datasource import ScopeError, check_patient_id, get_source
from . import structured
from .llm import ModelError, chat, embed, parse_json
from .retrieval import rank
from .router import route
from .validate import apply_verdicts, validate_grounding, validate_structure, verifier_messages

log = logging.getLogger("cliniq.assistant")

SYSTEM_PROMPT = """You are ClinIQ Nexus, a record-review assistant for physicians. The records are SYNTHETIC demonstration data.
Answer the question using ONLY the numbered sources below; all of them belong to the selected patient.
Return only JSON: {"claims":[{"kind":"documented","text":"...","citations":["S1"]}]}
Rules:
- 1 to 5 claims, most important first, each one sentence under 40 words.
- kind "documented": a fact explicitly stated in the cited sources. Cite every source that states it and only those.
- kind "not_documented": part of the question the sources do not answer. Say it is not documented in the available records and use empty citations. Missing information is never a negative finding: write "not documented", never "no" or "none".
- Copy numbers, units, doses and dates exactly as written in the sources.
- Do not state causes, explanations or conclusions unless a source states them explicitly.
- Refer to people as "the patient" or by clinical role (for example "the pulmonologist"); do not use gendered pronouns.
- Keep the documented reason for a visit (presenting symptoms) distinct from diagnoses recorded later in the assessment.
- When the question is about timing (first, initial, most recent, last), use the dates in the source labels and text to pick the correct encounter; do not describe a later visit as the first one.
- Do not diagnose, recommend or evaluate treatment, suggest dose changes, predict outcomes, or interpret images. Imaging reports describe synthetic test patterns; repeat only what the report text states.
- Do not put source labels like S1 inside the text."""

POLICY = {
    "policy_scope": "Questions are limited to the selected patient. Other patients' records are never searched, retrieved or sent to a model.",
    "policy_advice": "ClinIQ Nexus summarizes what is documented. It does not make diagnoses or treatment, dosing or prognosis recommendations. Related documentation is listed below for your review.",
    "policy_imaging": "The stored images are synthetic test patterns and ClinIQ Nexus does not interpret images. The documented imaging records and report text are shown below.",
}


def fact_sources(bundle: dict) -> list[dict]:
    """Structured records rendered as retrievable text so narrative answers can cite them."""
    pid = bundle["patient"]["patient_id"]
    out = []
    dx = {}
    for c in bundle["conditions"]:
        dx.setdefault(c["encounter_id"], []).append(f"{c['display']} ({c['code']}, {c['clinical_status']})")
    for e in bundle["encounters"]:
        text = (f"Encounter on {day(e['start_at'])}: {e['encounter_type']} ({e['class_display']}), {e['service']}, attending {e['attending']}. "
                f"Reason: {e['reason']}. Disposition: {e['disposition']}. Diagnoses: {'; '.join(dx.get(e['encounter_id'], [])) or 'none recorded'}. "
                f"Start {e['start_at'][:16].replace('T', ' ')} UTC, end {e['end_at'][:16].replace('T', ' ')} UTC.")
        out.append({"chunk_id": f"enc:{e['encounter_id']}", "patient_id": pid, "encounter_id": e["encounter_id"], "source_type": "encounter",
                    "source_id": e["encounter_id"], "document_id": None, "page_number": None,
                    "label": f"{e['encounter_type']} · {day(e['start_at'])}", "source_date": e["start_at"], "chunk_text": text})
    for m in bundle["medications"]:
        text = (f"Medication order {day(m['authored_on'])}: {m['medication']} {m['dose']} {m['route']} {m['frequency']} "
                f"({m['category']}, action {m['action']}, status {m['status']}). Reason: {m['reason']}."
                + (f" Ended {day(m['end_date'])}." if m["end_date"] else "") + (f" Stop reason: {m['stop_reason']}." if m["stop_reason"] else ""))
        out.append({"chunk_id": f"med:{m['medication_request_id']}", "patient_id": pid, "encounter_id": m["encounter_id"],
                    "source_type": "medication", "source_id": m["medication_request_id"], "document_id": None, "page_number": None,
                    "label": f"Medication order · {m['medication']} · {day(m['authored_on'])}", "source_date": m["authored_on"], "chunk_text": text})
    return out


def to_source(i: int, c: dict) -> dict:
    return {"sid": f"S{i}", "type": c["source_type"], "id": c["source_id"], "label": c["label"], "excerpt": c["chunk_text"],
            "date": c.get("source_date"), "page": c.get("page_number"), "document_id": c.get("document_id"),
            "encounter_id": c.get("encounter_id"), "score": c.get("score")}


def response(question, pid, route_name, intent, mode, claims, sources, t0, notice=None, validation=None, retrieval=None, model=None):
    return {"answer_id": uuid.uuid4().hex[:12], "question": question, "patient_id": pid, "route": route_name, "intent": intent,
            "mode": mode, "notice": notice, "claims": claims, "sources": sources,
            "validation": validation or {"passed": True, "checks": [], "level": "deterministic" if mode == "structured" else "n/a"},
            "retrieval": retrieval or {}, "model": model, "latency_ms": int((time.monotonic() - t0) * 1000)}


def retrieve(pid: str, question: str, bundle: dict, top_k: int = 8) -> tuple[list[dict], dict]:
    src = get_source()
    chunks = src.patient_rows("knowledge_chunks", pid)
    try:
        emb_rows = src.patient_rows("chunk_embeddings", pid)
    except Exception:
        emb_rows = []
    embeddings = {e["chunk_id"]: e["embedding"] for e in emb_rows
                  if isinstance(e.get("embedding"), list) and e["embedding"] and isinstance(e["embedding"][0], float)}
    candidates = chunks + fact_sources(bundle)
    if any(c["patient_id"] != pid for c in candidates):
        raise ScopeError("Retrieval candidate outside patient scope")
    qvec, embed_error = None, None
    if embeddings and settings.ai_enabled:
        try:
            qvec = embed(settings.embed_model, question)
        except ModelError as exc:
            embed_error = str(exc)
    if re.search(r"\b(first|initial|initially|originally|earliest|at the start|began)\b", question, re.I):
        recency: bool | str = "earliest"
    else:
        recency = bool(re.search(r"\b(recent|recently|latest|last|current|now)\b", question, re.I))
    ranked, mode = rank(question, candidates, embeddings, qvec, top_k=top_k, recency=recency)
    info = {"mode": mode, "candidates": len(candidates), "searched": dict(Counter(c["source_type"] for c in candidates)),
            "not_searchable": [f"{d['title']} (scanned, no text layer)" for d in bundle["documents"] if not d["has_text_layer"]],
            "embedding_model": settings.embed_model if mode == "hybrid" else None, "embedding_error": embed_error}
    return ranked, info


def ask(pid: str, question: str) -> dict:
    t0 = time.monotonic()
    check_patient_id(pid)
    question = (question or "").strip()[:500]
    if len(question) < 3:
        raise ValueError("Question is too short")
    bundle = patient_bundle(pid)
    route_name, intent = route(question, pid)

    if route_name == "policy_scope":
        return response(question, pid, route_name, None, "policy", [], [], t0, notice=POLICY[route_name])
    if route_name == "policy_imaging":
        b = structured.answer("imaging", bundle, question)
        return response(question, pid, route_name, "imaging", "policy", b.claims, b.sources, t0, notice=POLICY[route_name],
                        retrieval={"mode": "structured"})
    if route_name == "policy_advice":
        ranked, info = retrieve(pid, question, bundle, top_k=4)
        return response(question, pid, route_name, intent, "policy", [], [to_source(i, c) for i, c in enumerate(ranked, 1)], t0,
                        notice=POLICY[route_name], retrieval=info)
    if route_name == "structured":
        b = structured.answer(intent, bundle, question)
        return response(question, pid, route_name, intent, "structured", b.claims, b.sources, t0,
                        validation={"passed": True, "level": "deterministic",
                                    "checks": [{"name": "deterministic_source", "passed": True,
                                                "detail": "Built directly from structured records; no language model involved"}]},
                        retrieval={"mode": "structured"})

    ranked, info = retrieve(pid, question, bundle)
    sources = [to_source(i, c) for i, c in enumerate(ranked, 1)]
    if not ranked:
        return response(question, pid, route_name, intent, "no_evidence",
                        [{"kind": "not_documented", "text": "No documentation matching this question was found in the selected patient's records.", "citations": []}],
                        [], t0, retrieval=info)
    if not settings.ai_enabled:
        return response(question, pid, route_name, intent, "evidence_only", [], sources, t0,
                        notice="AI generation is disabled; showing the most relevant documented evidence.", retrieval=info)
    return generate(question, pid, bundle, sources, route_name, intent, info, t0)


def _attempt(model, messages, by_sid):
    """One generation + full validation pass. Returns (result, level, model_output) or raises ModelError."""
    out = chat(model, messages, max_tokens=1600)
    try:
        payload = parse_json(out["text"])
    except ValueError:
        payload = {}
    result = validate_structure(payload, set(by_sid), out["finish_reason"])
    if result.passed:
        result = validate_grounding(result, by_sid)
    level = "deterministic"
    if result.passed and any(c["kind"] == "documented" for c in result.claims):
        try:
            v = chat(settings.verifier_model, verifier_messages(result.claims, by_sid), max_tokens=600)
            result = apply_verdicts(result, parse_json(v["text"]).get("verdicts", []))
            level = "verified"
        except (ModelError, ValueError) as exc:
            result.ok("independent_verification", f"Verifier unavailable ({str(exc)[:80]}); deterministic grounding checks passed")
    return result, level


def generate(question, pid, bundle, sources, route_name, intent, info, t0):
    """Primary model first; if its answer is unavailable or rejected, one attempt with the fallback model.
    Every attempt is validated and verified independently — a retry never relaxes a safeguard."""
    by_sid = {s["sid"]: s for s in sources}
    patient = bundle["patient"]
    context = "\n\n".join(f"[{s['sid']}] {s['label']}\n{s['excerpt'][:1600]}" for s in sources)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Patient: {patient['display_name']} ({pid}). Records as of {day(bundle['as_of'])}.\n"
                                            f"Question: {question}\n\nSources:\n{context}"}]
    history, final, model_used = [], None, None
    for model in (settings.llm_model, settings.llm_fallback_model):
        try:
            result, level = _attempt(model, messages, by_sid)
        except ModelError as exc:
            history.append({"name": "model_available", "passed": False, "detail": f"{model}: {exc}"})
            continue
        model_used = model
        if result.passed:
            final = (result, level)
            break
        failed = "; ".join(c["detail"] for c in result.checks if not c["passed"])
        history.append({"name": "attempt_rejected", "passed": False, "detail": f"{model}: {failed}"[:400]})
        log.info("generation rejected patient=%s model=%s checks=%s", pid, model, [c["name"] for c in result.checks if not c["passed"]])
    if final is None:
        unavailable = all(h["name"] == "model_available" for h in history)
        notice = ("The language model is unavailable, so no generated answer is shown. The most relevant documented evidence is listed instead."
                  if unavailable else "Generated answers were produced but rejected by validation, so only documented evidence is shown. Reason: "
                  + "; ".join(h["detail"] for h in history)[:300])
        return response(question, pid, route_name, intent, "evidence_only", [], sources, t0, notice=notice,
                        validation={"passed": False, "level": "none" if unavailable else "rejected", "checks": history},
                        retrieval=info, model=model_used)
    result, level = final
    checks = [dict(h, name="earlier_attempt_rejected" if h["name"] == "attempt_rejected" else h["name"], passed=True,
                   detail=h["detail"] + " (superseded by a validated retry)") for h in history] + result.checks
    cited = {s for c in result.claims for s in c["citations"]}
    kept = [s for s in sources if s["sid"] in cited]
    return response(question, pid, route_name, intent, "generated", result.claims, kept, t0,
                    validation={"passed": True, "checks": checks, "level": level},
                    retrieval=dict(info, considered=len(sources)), model=model_used)


def suggestions(pid: str) -> list[dict]:
    b = patient_bundle(pid)
    out = []
    if any(e["class_code"] in ("IMP", "EMER") for e in b["encounters"]):
        out.append({"q": "What brought this patient to the hospital recently?", "kind": "narrative"})
    if any(d["doc_kind"] == "discharge_summary" for d in b["documents"]):
        out.append({"q": "What does the discharge summary document about the hospital course?", "kind": "narrative"})
    if any(t["status"] == "awaiting_reply" for t in b["threads"]):
        out.append({"q": "Are there portal messages awaiting a reply?", "kind": "structured"})
    if any(m["action"] in ("changed",) or m["status"] == "stopped" for m in b["medications"]):
        out.append({"q": "What medication changes are recorded?", "kind": "structured"})
    labs = Counter(o["name"] for o in b["observations"] if o["category"] == "laboratory")
    if labs:
        name, n = labs.most_common(1)[0]
        lab = name.split(" (")[0]
        lab = lab[0].lower() + lab[1:] if len(lab) > 1 and lab[1].islower() else lab
        out.append({"q": f"How has {lab} changed over time?" if n > 1 else "What are the latest laboratory results?", "kind": "structured"})
    out.append({"q": "How have the recorded vital signs changed?", "kind": "structured"})
    if b["follow_ups"]:
        out.append({"q": "What follow-up is documented and is any of it still open?", "kind": "structured"})
    if b["imaging"]:
        out.append({"q": "What imaging is available and what does the report say?", "kind": "structured"})
    out.append({"q": "What were the documented concerns at the last encounter?", "kind": "narrative"})
    out.append({"q": "What information cannot be established from the available records?", "kind": "structured"})
    return out[:8]
