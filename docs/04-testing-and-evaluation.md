# Testing and evaluation

Final release validation ran on 14 Oct 2026 against dataset `v5.0.0` (records as of 9 Oct 2026).

| Layer | Tool | Result |
|---|---|---|
| Offline unit and integration tests | `pytest tests` | **166 passed** |
| Cross-source clinical consistency audit | `tools/acceptance_audit.py` | **14/14 checks pass** (`docs/acceptance/acceptance-audit.json`) |
| Live AI evaluation (Unity Catalog + Foundation Model APIs) | `eval/run_eval.py` | **8/8 metrics pass** (`eval/results/latest.json`) |
| End-to-end HTTP acceptance on the primary app | `tools/acceptance_http.py` | **24/24 checks pass** (`docs/acceptance/main-app-acceptance.json`) |
| Rollback rehearsal | `tools/check_v4.py` | v4 redeployed and rendered with data, then v5 restored |

## 1. Offline tests: 166 passed

The tests read the locally built pipeline output. Model and embedding endpoints are **blocked** during tests, so every network-dependent path has to degrade correctly.

| Suite | Tests | What it proves |
|---|---|---|
| `test_pipeline_integrity.py` | 10 | All integrity checks pass. The misfiled PDF is quarantined and absent everywhere. Scanned PDFs have no text and no chunks. Every page prints its own patient ID. PDF chunks carry valid page numbers. No chunk mentions another patient. Unanswered threads are consistent. DICOM headers are verified and synthetic. BP readings are paired. |
| `test_isolation.py` | 30 | Bundles contain only the requested patient's rows and references. Requests for another patient's PDFs, pages and images return 404. The quarantined PDF is never served. Malformed IDs are rejected. Retrieval is patient-scoped. A foreign row raises `ScopeError`. Cross-patient questions are refused before retrieval. |
| `test_router.py` | 20 | 19 representative questions route correctly. A patient's own ID isn't treated as a scope violation. |
| `test_structured.py` | 75 | 7 structured questions × 10 patients are cited and scoped. Exact checks on medication changes, LDL trend, the awaiting-reply quote, imaging non-interpretation and gaps. |
| `test_validator.py` | 13 | The validator rejects: truncated output; unknown or missing citations; fabricated numbers and dates; citations that exist but don't support the claim; advice language; invented image findings; values in "not documented" claims; malformed payloads; verifier rejection. |
| `test_fallbacks.py` | 8 | Covers each fallback path: model unavailable, a hallucinated value, truncation, and verifier rejection each produce evidence only. A rejected primary answer gets **one** fully validated retry with the fallback model. Disabling AI produces evidence only, and an unrelated question produces "not documented". |
| `test_api.py` | 10 | API contract, worklist flags, brief composition, problem-list supersession, PDF bytes and pages, DICOM, operations, input validation, suggestions, and **no patient presented as currently admitted**. |

## 2. Cross-source clinical consistency audit: 14/14

`tools/acceptance_audit.py` reads the generated raw files (PDFs, DICOM) and the curated tables, and runs the backend read models.

| ID | Area | Check |
|---|---|---|
| AUD-01 | Identity | Note headers and every stated age ("58-year-old…") match demographics at the encounter date (47 checks) |
| AUD-02 | PDF | Every text page prints the filed patient, MRN and encounter (24 pages) |
| AUD-03 | Imaging | DICOM PatientID, name, birth date, sex, study date, accession, `OT`/`SYN`, burned-in flag and synthetic comment match the catalog |
| AUD-04 | Imaging | Reports reference their study and accession, and state that no interpretation exists |
| AUD-05 | Encounters | All encounters are finished, non-overlapping and end before the as-of date, **so no patient is currently admitted** |
| AUD-06 | Observations | Measurements fall inside their encounter. The only exception, labs drawn up to 5 days before a telehealth review, is documented. |
| AUD-07 | Observations | Lab flags agree with reference ranges; every value has a UCUM unit and LOINC code (366) |
| AUD-08 | Medications | Orders are authored within their encounter; dose-change chains and statuses agree with dates (44) |
| AUD-09 | PDF | Discharge-summary medication tables match the orders active at discharge |
| AUD-10 | PDF | Every lab value of the covered encounters appears on lab reports and discharge summaries (127) |
| AUD-11 | Care coordination | Follow-up statuses agree with the as-of date and with the encounters that resolve them |
| AUD-12 | Care coordination | Threads open with a patient message after the related encounter; summary fields match |
| AUD-13 | Physician brief | Every value stated in a brief item appears in the records it references (33 items) |
| AUD-14 | Worklist | Ages (as of the record date) and last-encounter dates match source records |

The narrative content was also cross-checked by hand. Examples:

- "weight down 5.8 kg since June" = 104.0 → 98.2;
- "clinic weight 81.9 kg, up 1.3 kg from 9/8" = 80.6 → 81.9;
- "seen 5 days after discharge" = 3 Sep → 8 Sep;
- consult-note vitals and labs match the encounter's observations.

## 3. Live AI evaluation: 39 questions

Configuration: `gpt-oss-120b` generator (`gpt-oss-20b` fallback), `llama-3.3-70b` verifier, `gte-large-en` embeddings, and the live `healthcare.cliniq_v5_stage` tables through the SQL warehouse.

The 39 questions break down as 18 narrative, 6 unsupported, 9 policy and 6 structured.

| Metric | Result |
|---|---|
| Patient isolation | **91/91** sources from the selected patient; 0 foreign or unresolvable |
| Citations resolve | **35** generated claims; 0 unresolved; 14 PDF page citations, all to pages that exist |
| Grounded answers accepted | **18/18** verified generations |
| Expected facts present | **17/18**. The one miss (physical-therapy progress) is an accurate answer that summarised progress without the specific measurements the keyword check looked for. |
| Unsupported not invented | **6/6** (allergies, rehab intake, echo ejection fraction, colonoscopy, family history, retinal exam) answered "not documented" |
| Policy routing | **9/9** advice, image-interpretation and cross-patient requests |
| Fabricated imaging findings | **0** |
| Median generation latency | **6.2 s** (retrieve + generate + validate + verify) |

### Issues found by reviewing answers, and fixed

Every generated claim was read against its cited sources:

1. **Gendered pronoun for a fictional clinician.** The model wrote "He recommended…". Fix: a prompt rule to refer to people by role. No pronouns appear in the final evaluation.
2. **Presenting complaint conflated with diagnosis.** "Initially presented with iron-deficiency anemia": the first visit was for fatigue and breathlessness, and anemia was the assessment. Fix: a prompt rule separating the visit reason from the diagnosis.
3. **Wrong encounter for "initially".** A temporal question was answered from a later visit. Fix: questions with first, initial or earliest now favour the earliest-dated sources in retrieval, plus a prompt rule to use source dates. Re-tested on three temporal questions; all correct.
4. **Intermittent rejections under rate limiting.** Two answers fell back to evidence only on the deployed app. Fix: one retry with the fallback model, fully validated and verified, and rejection reasons are now logged.

None of these fixes relaxed a safeguard: every accepted answer still passes all deterministic checks and the second-model verification.

## 4. End-to-end acceptance on the primary app: 24/24

`tools/acceptance_http.py` runs over HTTPS against `cliniq-nexus` after promotion. Data access uses the app's own service principal.

- **Access:** anonymous API calls return 401, and anonymous page requests are redirected to Databricks sign-in.
- **Runtime:** warehouse mode against `healthcare.cliniq_v5_stage`; all 10 application routes are served.
- **Isolation and status:** all 10 patients' bundles contain only their own rows, and no patient has an encounter in progress.
- **PDFs:** all 22 stream from the UC volume. Page counts and the printed patient identity match on every page, each PDF is refused under any other patient, and the quarantined PDF is not served.
- **Imaging:** all 10 DICOM studies render as `OT`/`SYN`.
- **Operations:** 14 integrity checks pass, and the evaluation scorecard is served.
- **Assistant:**
  - structured (2);
  - generated with PDF page citations and second-model verification (3);
  - unsupported → not documented (1);
  - advice, imaging and scope policies (3).

## 5. Manual UI review

Screenshots in `docs/screenshots/` were captured from the primary app at 1600×1000 and at 1024 px (tablet); the 1440-px layout was checked separately. The review covered:

- historical-only acute-care badges;
- the "No encounter in progress" status;
- synthetic labelling on every page;
- trend axes and units;
- PDF page citations;
- the imaging watermark;
- keyboard focus and Esc to close;
- layout at each width.

Fixes from this review:

- **Worklist:** replaced the ambiguous "Admitted" and "ED" badges.
- **Tab bar:** fixed clipping at 1440 px.
- **Architecture page:** brought up to date after promotion.
- **Labels:** corrected singular/plural message labels.

## 6. Security checks

See `docs/acceptance/security-audit.md`. It covers:

- secret scanning of the working tree and git history;
- static analysis (`bandit`);
- dependency audits (`pip-audit`, `npm audit`);
- PHI and synthetic-data review.

## Known gaps

- **Small dataset:** 10 synthetic patients means operational metrics are illustrative only.
- **Verifier dependency:** the verifier is a single LLM judgment. Deterministic checks reduce the risk, but human review remains necessary.
- **Accessibility:** checked manually (labels, focus, contrast tokens, table alternatives for charts). No automated axe audit was run.
