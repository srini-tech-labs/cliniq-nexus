# Final acceptance report: ClinIQ Nexus v5 release

**Date:** 14 Oct 2026. **Dataset:** `v5.0.0`, records as of 9 Oct 2026.

**Decision:** v5 accepted and promoted to the primary `cliniq-nexus` Databricks App. v4 is retained as a rehearsed rollback.

## A. Patient status and worklist accuracy

| Item | Finding | Resolution |
|---|---|---|
| "Admitted" and "ED" worklist badges | They showed acute care that **ended** in the last 120 days. Every encounter in the dataset has status `finished`, so "Admitted" wrongly implied a current hospitalization. | Replaced with historical labels ("Prior inpatient stay · 17 Sep", "Prior ED visit · 4 Aug"), with tooltips explaining they are not a current location. The filter is renamed "Hospital care · 120 days" and "Last seen" is now "Last encounter". |
| Current status | No explicit current-status indicator existed. | The patient header shows "No encounter in progress", derived from encounter status. A test asserts no patient is presented as currently admitted. |
| Brief acute-care item | The title read "Hospital admission · dates". | Now reads "Hospital admission (discharged) · dates" when the disposition is a discharge. |
| Names, ages, dates, scenarios, as-of date | Ages in every note match the birth date at the encounter date. Worklist ages are computed at the as-of date. Last-encounter dates match the source records. Relative times ("10 days ago", "waiting 4 days") use the as-of date. | Verified by AUD-01, AUD-14 and AUD-05. |

## B. Clinical consistency and AI grounding

Cross-source audit `tools/acceptance_audit.py`: **14/14 checks pass** (`acceptance-audit.json`).

| Area | Checks | Result |
|---|---|---|
| Encounters and diagnoses | Chronology, finished status, no overlaps; problem list keeps only the latest code per ICD category | Pass |
| Medications | Orders authored within their encounter; dose-change chains; statuses agree with dates; discharge-summary medication tables match orders | Pass |
| Labs and measurements | Values, dates, UCUM units, LOINC codes, H/L flags agree with reference ranges; every lab value appears on lab reports and discharge summaries | Pass |
| Notes and discharge summaries | Note values equal structured observations; stated ages and identities match | Pass |
| Portal communication | Status derivation, chronology, summary fields | Pass |
| PDFs | Each page's patient, MRN and encounter match the filing; quarantined document excluded everywhere | Pass |
| DICOM | Header identity, dates, accession, `OT`/`SYN`, burned-in synthetic text; report linkage | Pass |
| Physician brief | Every value in every brief item appears in the records it references; no diagnostic or treatment language | Pass |

**AI grounding** is covered by the live evaluation (39 questions) plus a manual review of every generated claim:

- isolation 91/91;
- 0 unresolved citations;
- 18/18 verified narrative answers;
- 6/6 unsupported questions answered "not documented";
- 9/9 policy routes;
- 0 imaging findings.

Three subtle issues found in review were fixed (a gendered pronoun, a complaint conflated with a diagnosis, the wrong encounter for "initially"), and the intermittent rejections under rate limiting were addressed with one validated fallback retry.

**Safeguards preserved:**

- patient isolation;
- citation checks;
- numeric and date grounding;
- second-model verification;
- evidence-only fallback;
- policy refusal of advice and image interpretation.

## C. Deployment and public-demo readiness

| Check | Result |
|---|---|
| Startup and runtime | The app starts; background warm-up pre-loads all ten patients; the first query after an idle warehouse takes 5–15 s. |
| Service-principal permissions | Least privilege: `USE CATALOG`; `USE SCHEMA` + `SELECT` on `cliniq_v5_stage`; `READ VOLUME` on its raw volume; `CAN_USE` on the warehouse; `CAN_QUERY` on four model endpoints. No write access. |
| SQL warehouse connectivity | Verified on both apps (warehouse mode, v5 schema). |
| Foundation-model quota handling | Paced embedding batches; 20 s SDK retry cap; validated fallback-model retry; lexical and evidence-only degradation. |
| PDF and DICOM access | 22/22 PDFs and 10/10 studies served from the UC volume; cross-patient and quarantined requests refused. |
| Configuration and credentials | All configuration via `app.yaml` and app resources; credentials injected by Databricks Apps; none in the repository. |
| Public access | **Not anonymously accessible.** Requests without a Databricks session are redirected to workspace sign-in (302), or receive 401 from the API. External recruiters can't open the app without a Databricks account in this workspace. **The portfolio uses screenshots and a recorded walkthrough video.** |
| Auto-stop | Free Edition apps stop 24 hours after a start or deploy. Run `databricks apps start cliniq-nexus` before a live demo. |

## Promotion and rollback

- **Promotion:** v5 deployed to `cliniq-nexus` from the release folder `app-v5`. HTTP acceptance passed **24/24** on the primary app.
- **Rollback rehearsal:** v4 redeployed to `cliniq-nexus` and rendered its dashboard with data, then v5 was restored and re-accepted at 24/24.
- **Candidate:** `cliniq-nexus-next` is retained with the identical build.
- **Procedure:** see `../03-deployment-and-rollback.md`.
