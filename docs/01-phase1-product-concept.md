# ClinIQ Nexus — Phase 1: Discovery & Product Concept

**Status:** Approved 2026-10-14 (D1-A, D2, D3, D4, plus D5: PDF clinical document intelligence) and implemented — see the architecture, testing and deployment documents · **Scope:** Synthetic demonstration only — not clinical decision support

---

## 1. Discovery findings (verified against the live workspace)

### 1.1 Infrastructure

| Resource | Finding | Implication |
|---|---|---|
| App `cliniq-nexus` | ACTIVE, Streamlit, single 419-line `app.py`, compute size MEDIUM, snapshot deployment from `/Workspace/Healthcare AI Agents/ClinIQ Nexus/app` | Backed up to `legacy/v4-app-backup/` + `legacy/v4-app-config.json`. Rollback = redeploy from the untouched source folder. |
| Other workspace app (unrelated project) | STOPPED | Out of scope; not touched. |
| App capacity | Free Edition allows **3 apps/account**; 2 exist; apps auto-stop after 24 h | One slot available for a candidate app (`cliniq-nexus-next`) alongside the live app. |
| SQL warehouse | Serverless Starter, 2X-Small, auto-stops (was STOPPED) | Cold start adds seconds to first query → app needs a "warming" state and in-process caching. |
| Service principal | `USE CATALOG healthcare`; `SELECT`+`USE SCHEMA` on `cliniq_v4_stage`, `cliniq_knowledge`; table-level SELECT on Gold resources; `READ VOLUME` on `source_files` | Read-only access already sufficient for the redesign on v4 data. |
| Model serving | READY pay-per-token endpoints: `databricks-gpt-oss-20b`, `gpt-oss-120b`, `llama-3-3-70b-instruct`, `qwen3-next-80b`, `llama-4-maverick`, others; **embeddings:** `databricks-gte-large-en`, `bge-large-en`, `qwen3-embedding-0-6b` | Model choice can be made empirically. In-app embedding rerank is possible at $0 without provisioning Vector Search. |

### 1.2 Data (v4 stage + retained Gold/imaging)

Counts match the brief: 10 patients · 25 encounters · 100 observations · 50 medication requests · 35 documents · 60 portal messages (30 threads) · 10 DICOM studies · 10 reports · 105 knowledge chunks.

**Integrity is strong.** Zero orphaned rows across observations, medications, documents, messages, imaging, and chunks (each row's `(patient_id, encounter_id)` resolves to a v4 encounter). No chunk text references a different patient. 100% `is_synthetic = true`.

**Clinical content is thin and templated.** This is the most important finding for product design:

| Area | Observed | Effect on the experience |
|---|---|---|
| Medications | Every request reads like *"Synthetic respiratory observation — example 1"*; all `completed`; no drug, dose, route, or change history | "What medications are recorded?" can only return placeholders; medication change tracking is impossible. |
| Portal messages | 3 identical threads per patient; every patient message answered by a templated clinic reply exactly 3 h later | Coordinator "open/unanswered message" workflow cannot be truthfully shown; turnaround metric is a constant. |
| Notes | One templated paragraph per encounter restating vitals; follow-up notes are generic | Assistant answers will be repetitive; little to "summarize". |
| Vitals | 4 vitals per encounter (HR, SpO₂, temperature, **systolic BP only**); 2–3 points per patient; narrow ranges | No true blood-pressure display (diastolic absent). Trends are 2–3-point comparisons, not trends. |
| Conditions | `cliniq_silver.conditions` (v3) labels every patient incl. the diabetes scenario as *"Respiratory symptom evaluation"* | Contradicts v4 scenarios → cannot be shown without misleading. |
| Encounter labels | Reasons like *"Diabetes follow-up follow-up"*; scenario P001 says "ED evaluation" but encounter class is `IMP`; P002 "monitoring visit" is `EMER` | Visible inconsistencies a clinician would notice immediately. |
| Imaging | 10 studies, modality `OT` (secondary capture), geometric images, one per patient, all at the last encounter; reports explicitly disclaim interpretation | Fine for a metadata/linkage demo; must be presented as test patterns. |
| Identity | `Demo SyntheticPatient001`, birth dates 1966–1975, clinical dates Jan–Apr 2026 | Clearly synthetic (good). "Recent" must be relative to the latest record, not today. |

**Conclusion:** the pipeline and integrity foundation are credible; the clinical *content* is not rich enough to make a polished clinical UI feel real. A beautiful interface over placeholder text would undermine the portfolio rather than help it. See decision **D1**.

---

## 2. Product definition

### 2.1 The clinical problem

**Pre-visit and transition-of-care chart review.** Before a follow-up visit or after a discharge, a clinician has to reconstruct *"what has happened to this patient since I last saw them"* from fragmented places: encounter history, progress notes, vitals flowsheets, medication lists, the portal inbox, and imaging reports. The work is slow, it's easy to miss things, and summaries written from memory are hard to trust.

**ClinIQ Nexus positioning:** *Every source in one longitudinal record, with a reviewable brief where each statement links to the document it came from.*

The product supports **review and information access**. It does not recommend, diagnose, or decide.

### 2.2 Personas and supported tasks

| Persona | Priority | Core question | Supported tasks (not decisions) |
|---|---|---|---|
| **Physician / clinical reviewer** | Primary | "What do I need to know before I see this patient?" | Scan brief → review recent encounters → compare vitals → check medications → read notes/reports → ask cited questions → see what is *not* documented |
| **Care coordinator** | Secondary | "Which communication loops are open, and what was the patient told?" | Thread chronology, routing status (when data supports it), follow-up instructions, evidence before outreach |
| **Clinical ops / IT leader** | Tertiary | "What does this platform unify, and how healthy is the data?" | Utilization, documentation/imaging coverage, portal volume and response time, integration and data-quality checks, architecture |

### 2.3 The 30-second message

> **Connected sources → patient context → cited answers.**
> One header line plus a three-step visual on the opening screen. A permanent *Synthetic data · Not for clinical use* badge sits in the app chrome, where it is visible but out of the way of the content.

---

## 3. Information architecture

```
ClinIQ Nexus
├── Patient Workspace (default)            ← physician-first
│   ├── Worklist rail (10 patients: episode label, last contact, source counts, open-item badge)
│   └── Patient record
│       ├── Brief         — context header, "since last encounter", vitals at a glance, sources inventory
│       ├── Journey       — chronological timeline; any event opens its source in the Evidence drawer
│       ├── Trends        — per-vital small multiples with units, reference context, sparsity notice
│       ├── Medications   — orders by encounter, status, change history (where data supports it)
│       ├── Communications— threads, chronology, routing/response status
│       └── Imaging       — study viewer + linked report, side by side
│   └── Ask the record    — persistent assistant panel, patient-scoped, available on every tab
├── Operations             ← leader view
│   ├── Activity & utilization
│   ├── Documentation & imaging coverage
│   ├── Communication patterns
│   └── Data quality & integration health (live checks)
└── How it works           ← hiring-manager view
    ├── Architecture (implemented v4/v5 vs proposed future, clearly separated)
    ├── AI safety contract (retrieval scope, validation, fallbacks)
    └── Evaluation scorecard (latest automated test results)
```

**Shared component: Evidence drawer.** Citations, timeline events, and assistant answers all open the same side drawer. It shows the source type, a human-readable label (*"Progress note · Respiratory assessment · 27 Jan 2026"*), the full text with the cited passage highlighted, the linked encounter, and lineage (*Volume file → Bronze → Silver → Knowledge chunk*) in a collapsed section. Raw IDs appear only in that collapsed section.

### Opening screen (wireframe, illustrative)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ ClinIQ Nexus   Workspace · Operations · How it works        ⓘ Synthetic data only │
├───────────────┬──────────────────────────────────────────────────┬───────────────────┤
│ WORKLIST  🔍  │ Synthetic Patient 003 · F · 58 · Post-discharge   │ ASK THE RECORD    │
│ ───────────── │ coordination · Last encounter 12 Mar 2026 (AMB)  │ Scoped to Pt 003  │
│ ● Pt 001 Resp │ ───────────────────────────────────────────────── │                   │
│   Pt 002 Diab │ SINCE ADMISSION (10 Feb)                          │ Suggested         │
│ ▶ Pt 003 Post │  ▸ Inpatient stay 32 h → 2 ambulatory follow-ups │ • Why was the     │
│   Pt 004 CV   │  ▸ 3 portal threads about discharge instructions │   pt admitted?    │
│   …           │  ▸ 1 imaging study with linked report            │ • What follow-up  │
│               │ ───────────────────────────────────────────────── │   was documented? │
│               │ VITALS (latest vs prior)   HR 88 ↘  SpO₂ 97% ↗ … │ • What did the    │
│               │ ───────────────────────────────────────────────── │   patient ask?    │
│               │ TIMELINE ──●────────●────────●──✉✉✉──▣────       │                   │
│               │           Feb10    Feb25    Mar12  msgs  img      │ [Ask a question…] │
│               │ SOURCES  4 notes · 6 messages · 1 study · 12 obs │                   │
└───────────────┴──────────────────────────────────────────────────┴───────────────────┘
```
*Layout and values are illustrative; final content comes from the records.*

On first load with no patient selected, the main area shows the three-step value story and a **"Start with a guided example"** button that opens a curated patient. A first-time user is inside a real patient record within one click.

---

## 4. Primary user journeys

**J1 — Physician pre-visit review (primary, target < 2 min)**
Worklist → select patient → read **Brief** (context, since-last-encounter, vitals at a glance) → open **Journey**, click the inpatient encounter → Evidence drawer shows the progress note → ask *"What follow-up instructions are documented?"* → cited answer → click citation → highlighted passage → check **Trends** for HR/SpO₂ across encounters → done.

**J2 — Care-coordinator loop closure**
Worklist filtered to *open communication* → patient → **Communications** shows threads in order with status chips (*Awaiting reply* / *Routed to care team* / *Answered*) → ask *"What was the patient told about follow-up?"* → cited answer from clinic replies and the follow-up note → evidence in hand before outreach.

**J3 — Leadership walkthrough**
**Operations** → encounter mix and activity → documentation and imaging coverage → portal response-time distribution → data-quality checks (each with a plain-language definition) → **How it works** → architecture and evaluation scorecard.

**J4 — Unsupported question (trust moment)**
*"Is the patient's pneumonia resolving?"* → assistant replies *"Not established from the available records"*, explains which source types were searched, and lists any related documented facts with citations. It does not invent a diagnosis.

---

## 5. AI assistant design ("Ask the record")

**Placement.** A persistent right-hand panel scoped to the selected patient. Switching patients clears the conversation with a visible notice. Suggested questions are built **deterministically from what exists** for that patient: there is no imaging question if there is no study, and no medication question if there are no orders.

**Answer contract.** The model returns structured JSON, not free text:
```json
{ "answer": [ {"kind": "documented",     "text": "...", "citations": ["S3","S5"]},
              {"kind": "not_documented", "text": "...", "citations": []} ],
  "searched": ["clinical_note","portal_message","radiology_report"] }
```
Each claim is shown with **citation chips that use human labels** (*Progress note · 27 Jan*). *Documented* and *Not documented* are visually distinct.

**Pipeline (all patient-scoped at the SQL layer before anything reaches Python or the model):**
1. **Route.** Structured questions (vitals, medications, encounters, imaging inventory) are answered **directly from tables** as cited fact cards, with no LLM involved. That is more reliable and costs nothing.
2. **Retrieve.** Narrative questions use lexical BM25 over the patient's chunks, optionally fused with **embedding similarity computed at request time** via `databricks-gte-large-en` over the patient's ≤ 20 chunks (see D4). This will be described accurately as *hybrid lexical + embedding reranking*, **not** managed Vector Search.
3. **Generate.** One model call with short labelled sources (`S1…Sn`, never cross-patient), with strict instructions: no diagnoses, treatment advice, or image interpretation.
4. **Validate (fail closed).** The answer is rejected if any of these checks fail:
   - The JSON parses and matches the schema.
   - The finish reason is `stop`, not a length cutoff.
   - Every `documented` claim cites at least one source, and every cited ID was retrieved for this patient.
   - Every number, date, and unit in a claim appears in its cited source (a numeric grounding check).
   - A deny-list check finds no diagnostic or treatment language that the sources don't contain.
   - The answer is within the length limit.
5. **Fallback.** On any failure the panel shows **evidence-only cards** (ranked excerpts with labels), plus a plain explanation of why no generated answer is shown.

**Kept from v4:** the patient-scope guard, the synthetic guard, citation-ID validation, the truncation guard, and the evidence-only fallback. All five carry forward as tested modules.

---

## 6. Imaging experience

The stored images are **synthetic geometric Secondary Capture (`OT`) objects**. The design is built around that fact:

- **Study list** per patient: modality (shown as *"OT · Secondary Capture"*), study date, linked encounter, report status.
- **Viewer:** server-rendered PNG from pydicom, with zoom/pan and window/level controls (showing that real DICOM handling works). A **persistent watermark band** reads *"Synthetic test pattern — not a medical image."*
- **DICOM metadata panel:** dimensions, bit depth, photometric interpretation, and SOP class, with UIDs collapsed.
- **Linked report** shown side by side with an explicit label: *"Report text is associated metadata; no AI image interpretation is performed."*
- The assistant may **quote** the report text with a citation. It never describes or interprets pixels.

**Future enhancement (deferred, separate approval):** a public, de-identified, openly licensed DICOM set for a real-image viewer demo. I will bring a short options memo covering license, de-identification provenance, size, compatibility, and ingestion steps, and import nothing until you approve.

---

## 7. Architecture and technology recommendation

### Recommended: one Databricks App — FastAPI backend + React/TypeScript SPA

```
Browser ──SSO (Databricks Apps proxy)──► Databricks App (Python, uvicorn)
                                          ├── /            static React build (prebuilt, shipped in source)
                                          └── /api/*       FastAPI
                                                ├── data      → SQL warehouse (databricks-sql-connector, bound params, table allowlist)
                                                ├── imaging   → UC Volume via SDK Files API → pydicom → PNG (cached)
                                                ├── assistant → retrieval + FM serving endpoint + validator
                                                └── ops/qa    → aggregate + integrity-check queries
                                          identity: app service principal (read-only grants)
```

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind with accessible headless primitives (Radix), TanStack Query, Recharts | Rich interaction (drawers, timelines, persistent assistant panel) that Streamlit's rerun model handles poorly; strong a11y primitives; widely recognised by hiring managers |
| Backend | FastAPI (Python 3.11) | Reuses the proven pydicom / databricks-sdk / sql-connector code; typed API; easy pytest coverage |
| Build | Frontend is built **locally**, and the static `dist/` is deployed with the source | No npm install at app startup, so deploys are faster and deterministic; one runtime, one process |
| Caching | In-process TTL cache per patient bundle + warm-up on start | Absorbs warehouse cold starts; 10-patient dataset fits easily in memory |
| Auth | Apps-managed SSO for users; app service principal for data | No secrets in code; matches the existing grants |

**Options considered and rejected:** a restyled Streamlit (limited layout and interaction; would still look like a notebook app); Dash (better, but the same ceiling for drawer/timeline UX); a Node/Next.js app (would duplicate the Python DICOM and SDK logic); Lakebase/Postgres (unnecessary; possible cost); managed Vector Search (unnecessary at ~100 chunks; possible capacity or cost limits).

**Cost:** $0 incremental. It reuses the existing warehouse, app compute, and pay-per-token FM endpoints, all within Free Edition quotas. Model calls happen only when the user asks a question.

---

## 8. Retain / redesign / defer

| Retain | Redesign | Defer |
|---|---|---|
| Medallion Delta tables & UC organization | Entire UI and navigation | Managed Vector Search |
| Read-only table allowlist, bound patient params | Assistant output contract (structured, claim-level) | Real public DICOM dataset (needs approval) |
| Synthetic-only guard, patient-scope guard | Retrieval (hybrid lexical + embedding rerank) | On-behalf-of-user auth / row-level security |
| Citation-ID + truncation validation, evidence fallback | Citation UX (human labels, highlighted passages) | Live FHIR API ingestion |
| pydicom rendering from UC Volume | Timeline, trends, imaging viewer, ops view | Agent/tool-calling frameworks |
| App SP + warehouse resource model | Validation (numeric grounding, deny-list, eval suite) | Multi-tenant / production hardening |

---

## 9. Demonstrating value, not just data

- **Time to understanding:** the Brief answers "what happened since the last encounter?" before anyone opens a table.
- **Trust by construction:** every assistant statement has a source a reviewer can open, and "not documented" is a first-class answer.
- **Honest gaps:** sparse trends and missing data are labelled as such, which is a clinical-safety feature in itself.
- **Integration made visible:** each source shows its lineage (file → Delta → knowledge chunk), and the Ops view runs live integrity checks.
- **Measured AI:** an evaluation scorecard (isolation, citation validity, refusal on unsupported questions, grounding) is regenerated by automated tests.

## 10. Communicating to technical hiring managers

1. An in-app **How it works** page with an architecture diagram that marks *Implemented* and *Proposed* components in different styles.
2. An **AI safety contract** page listing each guard and the test that proves it.
3. **Evaluation results** as a versioned artifact in the repo (and optionally logged to an MLflow experiment, which costs nothing on Free Edition).
4. A README with a screenshot tour, a 2-minute demo script, and a frank limitations section.
5. A one-page case study covering problem, constraints ($0, Free Edition), decisions, results, and what I would do next in production.

---

## 11. Implementation plan and gates

| Phase | Output | Gate |
|---|---|---|
| **1 — Discovery & concept** (this document) | Findings, product definition, IA, journeys, stack | **Approval: D1–D4** |
| 1b — Data enrichment *(if D1 = A)* | Generator notebook → new schema `healthcare.cliniq_v5_stage`; integrity checks; existing schemas untouched | Review the dataset profile |
| 2 — UX/UI design | Working clickable prototype (the real React frontend on fixture data) covering Workspace, Journey, Assistant, Imaging, Ops; published as a private page for review | **Approval** |
| 3 — Engineering | FastAPI + React app in `app/`, modular services, unit tests | — |
| 4 — Integration & evaluation | Live data wiring; pytest suite (isolation, adversarial cross-patient prompts, citation/truncation/grounding validators, unsupported-question refusals); golden question set across all patients; scorecard | Review results |
| 5 — Deployment | New workspace folder `…/ClinIQ Nexus/app-next`; deploy as candidate app `cliniq-nexus-next`; grant the same read-only access; smoke test; then either switch `cliniq-nexus` to the new source or keep both | **Approval before switching** |
| 6 — Portfolio | Screenshots, architecture diagram, README, case study, clean repo history | — |

**Rollback.** The legacy source folder is never modified. Switching is `databricks apps deploy cliniq-nexus --source-code-path <app-next>`, and rolling back is the same command pointed at the original `…/ClinIQ Nexus/app`. A local git backup of v4 already exists.

---

## 12. Decisions needed

**D1 — Clinical content (most consequential)**
- **A (recommended).** Generate a richer *synthetic* v5 dataset into a **new** schema `healthcare.cliniq_v5_stage` with the same 10 patients and IDs. It would add realistic fictional medication orders (drug, dose, frequency, start/stop/change), scenario-consistent conditions, diastolic BP and scenario-relevant labs (e.g. HbA1c and glucose for the diabetes patient, creatinine for the medication-reconciliation patient), 5–8 points for trend-focused patients, varied note sections (reason / findings / plan / follow-up), varied portal threads including some still awaiting reply, and discharge summaries. All content stays clearly labelled synthetic, and existing schemas stay untouched. *Cost:* serverless notebook run, $0. *Requires:* CREATE SCHEMA in `healthcare` (a write, but to a new schema only) plus a SELECT grant to the app SP.
- **B.** Keep v4 as is and design around the gaps. This is honest, but medication, communication-status, and trend features will look empty.

**D2 — Stack:** FastAPI + React/TypeScript in a single Databricks App (recommended), or keep a Python-only UI framework.

**D3 — Candidate deployment:** OK to create a third app, `cliniq-nexus-next`, in the free slot for side-by-side validation before switching? (It auto-stops after 24 h like the others.)

**D4 — Embedding rerank:** OK to call `databricks-gte-large-en` at request time over the selected patient's chunks? It uses Free Edition FM quota and adds no infrastructure.
