# Security and publication audit

Run on 14 Oct 2026 against the repository contents prepared for publication.

## 1. Secrets and sensitive configuration

I ran a pattern scan over every tracked text file, covering:

- Databricks PATs;
- OAuth and JWT tokens;
- GitHub and AWS keys;
- private keys;
- `client_secret` / `password` / `api_key` assignments;
- workspace host and workspace ID;
- app, service-principal and warehouse IDs;
- personal email addresses;
- AI-attribution markers.

**Result: no findings.** One internal warehouse ID in an acceptance-results file was redacted, and the tool that wrote it was changed to stop emitting it.

An independent scanner (`detect-secrets`, all files) reports only high-entropy hex strings in `data/v5/raw/manifest.json` and `data/v5/processed/knowledge_chunks.json`. These are SHA-256 content checksums, not secrets.

Binary metadata was reviewed:

- **PDFs:** author "ClinIQ Nexus synthetic data generator", producer ReportLab.
- **DICOM:** institution "Nexus General Hospital (fictional)", patient names `SYNTHETIC^PATIENTnnn`.
- **JPG/PNG:** no EXIF data.
- **Video:** encoder tags only.

How runtime credentials work:

- **App identity:** credentials are injected by Databricks Apps as service-principal OAuth.
- **Local development:** uses the developer's own CLI profile.
- **Repository:** contains neither. The warehouse ID is a deploy-time parameter (`tools/app_spec.template.json`, `tools/deploy.sh --warehouse`).

`.gitignore` excludes:

- local backups of the previous application and its configuration (`legacy/`), which contain account identifiers;
- the downloaded v4 DICOM files;
- build output (`build/`, `app/frontend/dist/`);
- `node_modules/`, `.venv/` and `.env*`.

## 2. Synthetic data and PHI

Every person and organisation in the dataset is fictional:

- **Patients:** "Synthetic Patient 001–010", MRNs `SYN-0000nn`.
- **Clinicians:** fictional names.
- **Hospital:** "Nexus General Hospital (fictional)".

Labelling:

- Every clinical row carries `is_synthetic = true`, and the application rejects any row without it.
- Every PDF page carries "SYNTHETIC DEMONSTRATION DOCUMENT — NOT FOR CLINICAL USE".
- The DICOM objects are geometric test patterns with `ConversionType = SYN`, burned-in "NOT A MEDICAL IMAGE" text, and synthetic patient names.

The scan found no SSN-like numbers, phone numbers or email addresses in the data. **No real PHI or protected hospital information exists anywhere in the repository.**

## 3. Static analysis (`bandit`)

| Finding | Assessment |
|---|---|
| B608: SQL built with an f-string (`datasource.py`) | False positive. The table identifier comes only from the constant `ALLOWED_TABLES` allowlist and is validated before use; patient IDs are bound parameters (`:pid`) and are also regex-validated. Annotated `# nosec B608` with that justification. |
| B110: `try/except/pass` when closing a broken SQL connection | Intentional; the connection is discarded. |
| B404/B603/B607: `subprocess` in `tools/` | Developer tooling only: fixed `databricks auth token` calls with no user input. Not part of the deployed app. |
| B311: `random` in `datagen/pdfs.py` | Used only for visual noise in synthetic scanned faxes; not security-relevant. |

## 4. Dependency audit

| Ecosystem | Before | Action | After |
|---|---|---|---|
| Python (`pip-audit`) | starlette 0.41.3 (via FastAPI 0.115.6): multiple advisories; pydicom 3.0.1: 1 advisory | Upgraded to FastAPI 0.143.1 (starlette 1.8.0) and pydicom 3.0.2 | 1 remaining: oauthlib 3.3.1 (see below) |
| npm (`npm audit --omit=dev`) | react-router-dom 6.28: 3 high, then 2 moderate on 6.30.6 | Upgraded to react-router-dom 7.18.4 (same component API); all routes and navigation re-tested on the deployed app | **0 vulnerabilities** |

**Accepted residual: oauthlib 3.3.1 (PYSEC-2026-4114).**

- The advisory is a timing side-channel in *server-side* PKCE verification for OAuth authorization servers.
- ClinIQ Nexus never acts as an OAuth server. oauthlib arrives only as a client-side dependency of `databricks-sql-connector`, and the connector's latest release (4.6.0) requires `oauthlib<4`.
- Re-assess when the connector allows oauthlib 4.

After the upgrades: 166 offline tests pass, the main app passes 24/24 HTTP acceptance checks, and in-app navigation was re-tested.

## 5. Application security controls (verified)

- **Read-only data access:** the service principal holds `SELECT` on `cliniq_v5_stage`, `READ VOLUME` on its raw volume, and `CAN_QUERY` on four model endpoints. It has no write privileges.
- **Patient-bound reads:** every patient read uses a bound SQL parameter and a row-level re-check (`ScopeError`). Files are served only after a document or study ownership check, and the DICOM header patient is re-verified.
- **No anonymous access:** anonymous requests are redirected to Databricks sign-in or receive 401 (verified by `tools/acceptance_http.py`).
- **Response headers:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: SAMEORIGIN`, and `Cache-Control: no-store` on API responses.
- **Input limits:** questions are 3–500 characters, and malformed patient IDs are rejected with 400/404.
- **No patient communication:** the app doesn't send messages and never writes clinical data.

## 6. Git history and identity

- **Identity:** every commit's author and committer is `srini-venkataraman <332990115+srini-venkataraman@users.noreply.github.com>`.
- **Attribution:** no AI co-author trailers, generated-by markers or assistant attribution in commit messages or files (scanned).
- **Clean history:** the history was prepared locally and never pushed. It is a single commit, with superseded local commits and objects pruned (`git fsck` reports no unreachable objects). Files excluded by `.gitignore` (`legacy/`, `data/source_dicom/`, `planning/`, build output) are verified ignored and absent from the commit.
- **Final verification from a fresh clone of the release commit:** 185 files (31.2 MB), 166 tests pass, consistency audit 14/14, frontend build succeeds, `npm audit` reports 0, and `pip-audit` shows the single documented oauthlib residual.
