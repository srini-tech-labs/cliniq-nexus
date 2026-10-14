# ClinIQ Nexus: executive summary

**A physician-centered clinical intelligence prototype on a governed Databricks lakehouse, with evidence-grounded AI.**
*Synthetic data only; a technology demonstration, not a clinical system.*

![ClinIQ Nexus physician brief](images/01-physician-brief.jpg)

## The problem

Before a follow-up visit or after a hospital discharge, a clinician has to piece together what has happened to a patient. That information is fragmented across:

- encounters;
- clinical notes;
- laboratory results and vital signs;
- medication orders;
- PDF discharge summaries and consult letters;
- patient-portal messages;
- imaging records.

Each source answers part of the question. None of them shows what matters or where the supporting evidence is.

## The solution

ClinIQ Nexus brings these sources into one patient-scoped workspace on Databricks, built around a single question: *What has happened with this patient, what matters, and where is the evidence?*

- **Physician brief:** a list of items needing attention, derived from the records. Each item links to its source: a recent admission, unanswered portal messages, medication changes, results outside reference ranges, overdue follow-up, documents that cannot be searched.
- **Longitudinal journey:** encounters and their linked notes, PDFs, medications, results, messages and imaging on one timeline.
- **Trends and medication history:** unit-aware charts and a medication timeline built from structured orders.
- **PDF document intelligence:** page-level extraction, patient-identity verification on every page, quarantine of misfiled documents, and citations that open the PDF on the cited page.
- **Imaging:** DICOM viewing and metadata linked to orders and reports, clearly labelled as synthetic test patterns and never interpreted.
- **Ask the record:** an AI assistant restricted to the selected patient.
  - Factual questions are answered directly from records.
  - Narrative answers must cite their sources and pass deterministic grounding checks and a second-model verification. Otherwise only the evidence is shown.
  - The assistant declines diagnosis, treatment and dosing requests.

## How it is built

- **Platform:** Databricks Free Edition with Unity Catalog, Delta Lake, a managed volume, a serverless ingestion notebook, a serverless SQL warehouse, Databricks Apps, and pay-per-token Foundation Model APIs. No additional paid infrastructure.
- **Data:** synthetic FHIR-style data (Patient, Encounter, Condition, Observation, MedicationRequest, Communication, ImagingStudy) with clinical PDFs and DICOM objects. Narrative documents are generated from the same structured facts, so values stay consistent across sources.
- **Application:** a FastAPI backend and a React/TypeScript frontend, deployed as one Databricks App with read-only, least-privilege access.

## What was demonstrated

This is a working prototype, deployed as the primary `cliniq-nexus` Databricks App and validated with:

- 166 automated tests;
- a 14-point cross-source clinical consistency audit;
- a 39-question live AI evaluation: all cited sources from the correct patient, no unresolved citations, no invented answers to unsupported questions, no imaging interpretations;
- a 24-check end-to-end acceptance suite on the deployed app;
- a rehearsed one-command rollback to the previous version.

No productivity, clinical-outcome or financial claims are made. The prototype demonstrates integrated clinical context, longitudinal review, document traceability and source-supported answers on synthetic data.

## Boundaries

ClinIQ Nexus is **not** a production clinical system, an EHR integration, a diagnostic tool or HIPAA-certified software. The app sits behind Databricks single sign-on, so it is shown through screenshots and a recorded walkthrough.
