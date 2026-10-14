"""Graceful degradation: model, embedding and validation failures never produce an unvalidated answer."""
import json

from backend.assistant import service


def ask(pid="CN-P003", q="What does the discharge summary document about the hospital course?"):
    return service.ask(pid, q)


def test_model_unavailable_gives_evidence_only():
    r = ask()
    assert r["mode"] == "evidence_only" and r["claims"] == [] and r["sources"]
    assert r["retrieval"]["mode"] == "lexical"
    assert "unavailable" in r["notice"]


def _chat_returning(payloads):
    calls = iter(payloads)

    def fake(model, messages, max_tokens=1200, temperature=0.0, timeout_s=60):
        text, finish = next(calls)
        return {"text": text, "finish_reason": finish, "usage": {}, "latency_ms": 5, "model": model}
    return fake


def _sources_for(pid, q):
    from backend.clinical import patient_bundle
    ranked, _ = service.retrieve(pid, q, patient_bundle(pid))
    return [service.to_source(i, c) for i, c in enumerate(ranked, 1)]


def test_valid_generation_with_verifier_is_accepted(monkeypatch):
    q = "What does the discharge summary document about the hospital course?"
    srcs = _sources_for("CN-P003", q)
    sid = next(s["sid"] for s in srcs if "84.2 kg" in s["excerpt"])
    answer = json.dumps({"claims": [{"kind": "documented", "text": "Admission weight was 84.2 kg and BNP was 1480 pg/mL.", "citations": [sid]}]})
    verdict = json.dumps({"verdicts": [{"id": 1, "supported": True}]})
    monkeypatch.setattr(service, "chat", _chat_returning([(answer, "stop"), (verdict, "stop")]))
    r = ask(q=q)
    assert r["mode"] == "generated" and r["validation"]["passed"] and r["validation"]["level"] == "verified"
    assert [s["sid"] for s in r["sources"]] == [sid]


def test_hallucinated_value_is_rejected_to_evidence_only(monkeypatch):
    q = "What does the discharge summary document about the hospital course?"
    srcs = _sources_for("CN-P003", q)
    sid = srcs[0]["sid"]
    answer = json.dumps({"claims": [{"kind": "documented", "text": "BNP was 2900 pg/mL on admission.", "citations": [sid]}]})
    monkeypatch.setattr(service, "chat", _chat_returning([(answer, "stop"), (answer, "stop")]))
    r = ask(q=q)
    assert r["mode"] == "evidence_only" and r["claims"] == [] and not r["validation"]["passed"]


def test_truncated_generation_is_rejected(monkeypatch):
    bad = ('{"claims":[{"kind":"documented","text":"The patient was', "length")
    monkeypatch.setattr(service, "chat", _chat_returning([bad, bad]))
    r = ask()
    assert r["mode"] == "evidence_only"


def test_verifier_rejection_blocks_answer(monkeypatch):
    q = "What does the discharge summary document about the hospital course?"
    srcs = _sources_for("CN-P003", q)
    sid = next(s["sid"] for s in srcs if "84.2 kg" in s["excerpt"])
    answer = json.dumps({"claims": [{"kind": "documented", "text": "Admission weight was 84.2 kg.", "citations": [sid]}]})
    verdict = json.dumps({"verdicts": [{"id": 1, "supported": False, "reason": "wrong"}]})
    monkeypatch.setattr(service, "chat", _chat_returning([(answer, "stop"), (verdict, "stop"), (answer, "stop"), (verdict, "stop")]))
    assert ask(q=q)["mode"] == "evidence_only"


def test_rejected_primary_is_retried_once_with_fallback_and_fully_validated(monkeypatch):
    q = "What does the discharge summary document about the hospital course?"
    srcs = _sources_for("CN-P003", q)
    sid = next(s["sid"] for s in srcs if "84.2 kg" in s["excerpt"])
    bad = json.dumps({"claims": [{"kind": "documented", "text": "Admission weight was 99.9 kg.", "citations": [sid]}]})
    good = json.dumps({"claims": [{"kind": "documented", "text": "Admission weight was 84.2 kg.", "citations": [sid]}]})
    verdict = json.dumps({"verdicts": [{"id": 1, "supported": True}]})
    calls = []
    fake = _chat_returning([(bad, "stop"), (good, "stop"), (verdict, "stop")])
    monkeypatch.setattr(service, "chat", lambda model, *a, **k: calls.append(model) or fake(model, *a, **k))
    r = ask(q=q)
    assert r["mode"] == "generated" and r["validation"]["level"] == "verified"
    assert calls[:2] == [service.settings.llm_model, service.settings.llm_fallback_model]
    assert any(c["name"] == "earlier_attempt_rejected" for c in r["validation"]["checks"])


def test_ai_disabled_returns_evidence(monkeypatch):
    monkeypatch.setattr(service, "settings", type("S", (), {**{k: getattr(service.settings, k) for k in dir(service.settings) if not k.startswith("_")}, "ai_enabled": False})())
    assert ask()["mode"] == "evidence_only"


def test_unrelated_question_returns_not_documented():
    r = service.ask("CN-P005", "What is the patient's favourite food?")
    assert r["mode"] == "no_evidence" and r["claims"][0]["kind"] == "not_documented"
