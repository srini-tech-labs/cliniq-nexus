"""Fail-closed validation of generated answers against their cited evidence.

A citation identifier existing is not treated as verification. Each documented claim must
also pass numeric/date grounding and lexical support checks against the text of the
sources it cites, contain no unsupported advice or image-interpretation language, and
(when available) be judged supported by an independent verifier model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retrieval import normalize, tokens

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})"), lambda m: (int(m[2]), int(m[3]))),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b"), lambda m: (int(m[1]), int(m[2]))),
    (re.compile(MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*\d{4})?", re.I), lambda m: (MONTHS[m[1][:3].lower()], int(m[2]))),
    (re.compile(r"\b(\d{1,2})\s+" + MONTH_RE + r"\.?(?:\s+\d{4})?", re.I), lambda m: (MONTHS[m[2][:3].lower()], int(m[1]))),
]
NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")
ADVICE = re.compile(r"\b(you should|should (be|start|stop|increase|decrease|consider)|we recommend|i recommend|recommend(ed)? (that|starting|stopping)"
                    r"|consider (starting|stopping|increasing|decreasing|adding)|it is safe|is likely|probably|suggests? (that )?the patient has)\b", re.I)
IMAGE_WORDS = re.compile(r"\b(opacit\w*|infiltrat\w*|consolidat\w*|effusion|fracture|cardiomegaly|nodule|mass|lesion|abnormalit\w*|unremarkable|normal (study|exam|image|radiograph))\b", re.I)
SUPPORT_THRESHOLD = 0.5
MAX_CLAIMS, MAX_WORDS = 6, 60


@dataclass
class Result:
    passed: bool
    checks: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)

    def fail(self, name: str, detail: str):
        self.checks.append({"name": name, "passed": False, "detail": detail})
        self.passed = False

    def ok(self, name: str, detail: str = ""):
        self.checks.append({"name": name, "passed": True, "detail": detail})


def extract_dates(text: str) -> tuple[set[tuple[int, int]], str]:
    found, rest = set(), text
    for pattern, conv in DATE_PATTERNS:
        for m in pattern.finditer(rest):
            try:
                md = conv(m)
                if 1 <= md[0] <= 12 and 1 <= md[1] <= 31:
                    found.add(md)
            except (KeyError, ValueError):
                pass
        rest = pattern.sub(" ", rest)
    return found, rest


def numbers(text: str) -> set[str]:
    out = set()
    for n in NUMBER.findall(text):
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def validate_structure(payload: dict, source_ids: set[str], finish_reason: str | None) -> Result:
    r = Result(passed=True)
    if finish_reason not in ("stop", "end_turn", None):
        r.fail("complete_generation", f"Generation ended with finish_reason={finish_reason}; truncated output is rejected")
    else:
        r.ok("complete_generation")
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list) or not claims:
        r.fail("schema", "No claims array")
        return r
    if len(claims) > MAX_CLAIMS:
        r.fail("length", f"{len(claims)} claims exceeds limit of {MAX_CLAIMS}")
    clean = []
    for i, c in enumerate(claims, start=1):
        if not isinstance(c, dict) or c.get("kind") not in ("documented", "not_documented") or not isinstance(c.get("text"), str):
            r.fail("schema", f"Claim {i} is malformed")
            continue
        text = c["text"].strip()
        cites = [s for s in (c.get("citations") or []) if isinstance(s, str)]
        if not text:
            continue  # tolerate empty placeholder claims; they are dropped
        if len(text.split()) > MAX_WORDS:
            r.fail("length", f"Claim {i} exceeds {MAX_WORDS} words")
        if c["kind"] == "documented" and not cites:
            r.fail("citation_present", f"Documented claim {i} has no citation")
        unknown = [s for s in cites if s not in source_ids]
        if unknown:
            r.fail("citation_known", f"Claim {i} cites unknown source(s) {unknown}")
        clean.append({"kind": c["kind"], "text": text, "citations": [s for s in cites if s in source_ids]})
    if not clean:
        r.fail("schema", "All claims empty")
    if r.passed:
        r.ok("schema", f"{len(clean)} claims")
        r.ok("citation_known", "All citations refer to retrieved patient sources")
    r.claims = clean
    return r


def validate_grounding(result: Result, sources: dict[str, dict]) -> Result:
    """Check each documented claim against the concatenated text of the sources it cites."""
    problems = []
    for i, c in enumerate(result.claims, start=1):
        if c["kind"] != "documented":
            if NUMBER.search(extract_dates(c["text"])[1]):
                problems.append(("grounding_numbers", f"Not-documented claim {i} asserts a numeric value"))
            continue
        evidence = normalize(" ".join(sources[s]["excerpt"] for s in c["citations"]))
        claim = normalize(c["text"])
        c_dates, c_rest = extract_dates(claim)
        e_dates, _ = extract_dates(evidence)
        missing_dates = c_dates - e_dates
        if missing_dates:
            problems.append(("grounding_dates", f"Claim {i} date(s) {sorted(missing_dates)} not found in cited sources"))
        e_numbers = numbers(evidence)
        missing_nums = {n for n in numbers(c_rest) if n not in e_numbers}
        if missing_nums:
            problems.append(("grounding_numbers", f"Claim {i} value(s) {sorted(missing_nums)} not found in cited sources"))
        c_tok = set(tokens(c_rest))
        e_tok = set(tokens(evidence))
        if c_tok:
            support = len(c_tok & e_tok) / len(c_tok)
            c["support"] = round(support, 2)
            if support < SUPPORT_THRESHOLD:
                problems.append(("lexical_support", f"Claim {i} has low overlap with cited sources ({support:.0%})"))
        if ADVICE.search(claim) and not ADVICE.search(evidence):
            problems.append(("no_advice", f"Claim {i} contains recommendation or inference language not present in the sources"))
        image_terms = ({m.group(0).lower() for m in IMAGE_WORDS.finditer(claim)}
                       - {m.group(0).lower() for m in IMAGE_WORDS.finditer(evidence)})
        if image_terms:
            problems.append(("no_image_interpretation", f"Claim {i} uses imaging-finding terms not in the sources: {sorted(image_terms)}"))
    names = ["grounding_dates", "grounding_numbers", "lexical_support", "no_advice", "no_image_interpretation"]
    for name in names:
        hits = [d for n, d in problems if n == name]
        if hits:
            result.fail(name, "; ".join(hits))
        else:
            result.ok(name)
    return result


VERIFIER_PROMPT = """You check whether statements are fully supported by the quoted source text from a SYNTHETIC medical record.
For each numbered statement answer supported=true only if every fact in it (values, dates, actions, who did what) is explicitly stated in its sources. Paraphrase is fine; added facts, inferences, or stronger claims are not.
Return only JSON: {"verdicts":[{"id":1,"supported":true,"reason":"short"}]}"""


def verifier_messages(claims: list[dict], sources: dict[str, dict]) -> list[dict]:
    parts = []
    for i, c in enumerate(claims, start=1):
        if c["kind"] != "documented":
            continue
        src = "\n".join(f"<<{s}: {sources[s]['excerpt'][:1500]}>>" for s in c["citations"])
        parts.append(f"Statement {i}: {c['text']}\nSources:\n{src}")
    return [{"role": "system", "content": VERIFIER_PROMPT}, {"role": "user", "content": "\n\n".join(parts)}]


def apply_verdicts(result: Result, verdicts: list[dict]) -> Result:
    documented = {i for i, c in enumerate(result.claims, start=1) if c["kind"] == "documented"}
    seen, bad = set(), []
    for v in verdicts:
        try:
            idx = int(v.get("id"))
        except (TypeError, ValueError):
            continue
        seen.add(idx)
        if idx in documented and v.get("supported") is not True:
            bad.append(f"Claim {idx}: {str(v.get('reason', 'not supported'))[:120]}")
    if documented - seen:
        bad.append(f"Verifier returned no verdict for claim(s) {sorted(documented - seen)}")
    if bad:
        result.fail("independent_verification", "; ".join(bad))
    else:
        result.ok("independent_verification", "All documented claims judged supported by the verifier model")
    return result
