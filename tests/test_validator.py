"""The validator rejects incomplete, uncited, unknown-cited, ungrounded and out-of-policy answers."""
from backend.assistant.validate import apply_verdicts, validate_grounding, validate_structure

SOURCES = {
    "S1": {"excerpt": "Discharge Summary (3 Sep 2026), page 1. Weight decreased to 80.1 kg at discharge and BNP decreased to 620 pg/mL. Oral furosemide was increased from 20 mg to 40 mg daily on 9/3/2026."},
    "S2": {"excerpt": "Imaging report. Findings: None reported. The stored image is not a medical image and was not interpreted."},
}


def run(claims, finish="stop"):
    r = validate_structure({"claims": claims}, set(SOURCES), finish)
    return validate_grounding(r, SOURCES) if r.passed else r


def failed(r):
    return {c["name"] for c in r.checks if not c["passed"]}


def test_valid_answer_passes():
    r = run([{"kind": "documented", "text": "Furosemide was increased from 20 mg to 40 mg daily on 9/3/2026.", "citations": ["S1"]},
             {"kind": "not_documented", "text": "A follow-up echocardiogram is not documented in the available records.", "citations": []}])
    assert r.passed, r.checks


def test_paraphrased_date_format_is_accepted():
    assert run([{"kind": "documented", "text": "Discharge weight was 80.1 kg on September 3, 2026.", "citations": ["S1"]}]).passed


def test_truncated_generation_rejected():
    assert "complete_generation" in failed(run([{"kind": "documented", "text": "Weight was 80.1 kg.", "citations": ["S1"]}], finish="length"))


def test_unknown_citation_rejected():
    assert "citation_known" in failed(run([{"kind": "documented", "text": "Weight was 80.1 kg.", "citations": ["S9"]}]))


def test_missing_citation_rejected():
    assert "citation_present" in failed(run([{"kind": "documented", "text": "Weight was 80.1 kg.", "citations": []}]))


def test_fabricated_number_rejected():
    assert "grounding_numbers" in failed(run([{"kind": "documented", "text": "BNP decreased to 410 pg/mL at discharge.", "citations": ["S1"]}]))


def test_fabricated_date_rejected():
    assert "grounding_dates" in failed(run([{"kind": "documented", "text": "Furosemide was increased on 9/5/2026.", "citations": ["S1"]}]))


def test_citation_that_does_not_support_claim_rejected():
    # Citation ID exists, but the cited text is about imaging, not weight: lexical support fails.
    assert "lexical_support" in failed(run([{"kind": "documented", "text": "Diuresis with furosemide reduced weight substantially before discharge.", "citations": ["S2"]}]))


def test_advice_language_rejected():
    assert "no_advice" in failed(run([{"kind": "documented", "text": "You should increase furosemide to 40 mg daily.", "citations": ["S1"]}]))


def test_invented_image_finding_rejected():
    assert "no_image_interpretation" in failed(run([{"kind": "documented", "text": "The image was not interpreted and shows no effusion.", "citations": ["S2"]}]))


def test_not_documented_claim_cannot_assert_values():
    assert "grounding_numbers" in failed(run([{"kind": "not_documented", "text": "BNP of 300 is not documented.", "citations": []}]))


def test_empty_or_malformed_payload_rejected():
    assert not validate_structure({}, set(SOURCES), "stop").passed
    assert not validate_structure({"claims": [{"kind": "guess", "text": "x"}]}, set(SOURCES), "stop").passed


def test_verifier_unsupported_or_missing_verdict_rejected():
    r = run([{"kind": "documented", "text": "Weight decreased to 80.1 kg at discharge.", "citations": ["S1"]},
             {"kind": "documented", "text": "BNP decreased to 620 pg/mL.", "citations": ["S1"]}])
    assert r.passed
    bad = apply_verdicts(r, [{"id": 1, "supported": True}, {"id": 2, "supported": False, "reason": "not stated"}])
    assert not bad.passed
    r2 = run([{"kind": "documented", "text": "Weight decreased to 80.1 kg at discharge.", "citations": ["S1"]}])
    assert not apply_verdicts(r2, []).passed
