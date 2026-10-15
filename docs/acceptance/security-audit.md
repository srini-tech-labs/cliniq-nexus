# Security and publication audit

Run on 14 Oct 2026 against the repository contents prepared for publication, and re-run on 14 Oct 2026 for the follow-up commit that upgrades pypdf and corrects post-promotion state (sections 4 and 6).

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
| B101: `assert` in `tools/smoke_test.py` | Developer smoke test; the assertion is the test check itself. Not part of the deployed app. |
| B311: `random` in `datagen/pdfs.py` | Used only for visual noise in synthetic scanned faxes; not security-relevant. |

## 4. Dependency audit

| Ecosystem | Before | Action | After |
|---|---|---|---|
| Python (`pip-audit`) | starlette 0.41.3 (via FastAPI 0.115.6): multiple advisories; pydicom 3.0.1: 1 advisory | Upgraded to FastAPI 0.143.1 (starlette 1.8.0) and pydicom 3.0.2 | 1 remaining: oauthlib 3.3.1 (see below) |
| Python, development and ingestion tooling (`pip-audit -r requirements-dev.txt`) | pypdf 5.1.0: 49 advisories (fixed in 6.7.1 to 6.19.0) | Upgraded to pypdf 6.19.0 in `requirements-dev.txt` and in the ingestion notebook's `%pip` line (with pydicom 3.0.2, matching the app). pypdf is used only by the local pipeline, the ingestion notebook and the consistency audit; the deployed app does not install or import it | 1 remaining: the same oauthlib 3.3.1 residual |
| npm, runtime packages (`npm audit --omit=dev`) | react-router-dom 6.28: 3 high, then 2 moderate on 6.30.6 | Upgraded to react-router-dom 7.18.4 (same component API); all routes and navigation re-tested on the deployed app | **0 runtime vulnerabilities** |
| npm, including build/dev tooling (`npm audit`) | 10 findings (7 high, 3 moderate) | Non-major updates: postcss 8.4.49 → 8.5.28 (fixes all four PostCSS advisories) and vite 5.4.11 → 5.4.21 (latest 5.x; fixes 9 of its 12 advisories). No application changes; the production bundle is byte-identical | 9 findings (6 high, 3 moderate), all in build/dev tooling; every remaining fix is a major upgrade |

**Accepted residual: oauthlib 3.3.1 (PYSEC-2026-4114).**

- The advisory is a timing side-channel in *server-side* PKCE verification for OAuth authorization servers.
- ClinIQ Nexus never acts as an OAuth server. oauthlib arrives only as a client-side dependency of `databricks-sql-connector`, and the connector's latest release (4.6.0) requires `oauthlib<4`.
- Re-assess when the connector allows oauthlib 4.

**pypdf 6.19.0 and the committed data.** The committed processed data and the deployed Delta tables were produced with pypdf 5.1.0. Re-running `pipeline/cliniq_pipeline.py` with 6.19.0 changes only whitespace in the extracted text (24 of 27 pages gain leading spaces on some lines). After whitespace normalisation the text is identical, and all 166 tests and the 14 consistency checks pass with 6.19.0. The data has not been regenerated or redeployed; the next ingestion run will pick up the new extractor.

**Build/dev-only npm findings (not shipped).** The full `npm audit`, including development dependencies, reports 9 findings. None of these packages is present in the deployed app, which serves only the prebuilt static bundle in `frontend/dist`:

| Package | Severity | Path | Remaining advisories | Available fix |
|---|---|---|---|---|
| tailwindcss 3.4.16 | high | direct (CSS build) | via the dependencies below | 4.x only (major) |
| braces, chokidar, fast-glob, micromatch | high | via tailwindcss 3 (file watching and globbing) | — | via tailwindcss 4 (major) |
| postcss-nested, postcss-selector-parser | moderate | via tailwindcss 3 | — | via tailwindcss 4 (major) |
| vite 5.4.21 | high | direct (dev server and bundler) | GHSA-4w7w-66w2-5vf9 (optimized-deps `.map` path traversal, dev server); GHSA-v6wh-96g9-6wx3 and GHSA-fx2h-pf6j-xcff (Windows-only dev-server issues) | 6.4.3+ (major) |
| esbuild 0.21.5 | moderate | via vite (dev server) | GHSA-67mh-4wv8-2f99 (dev server readable by other websites) | via a vite major |

A Tailwind 4 migration and a Vite major upgrade are breaking changes to the build and have deliberately **not** been made without owner approval. The remaining vite and esbuild advisories affect only the local development server (`npm run dev`), which runs on a developer's machine and is never exposed by the deployed app; `vite build` output does not contain them.

**Test client.** Starlette 1.8's `TestClient` warns when it falls back to `httpx`. The development requirements now include `httpx2` 2.13.1 (with its dependencies `httpcore2` 2.13.1 and `truststore` 0.10.5), which the test client uses instead, so the test run is warning-free. `httpx` 0.28.1 is kept for `tools/acceptance_http.py` and `tools/smoke_test.py`. None of these packages is installed in the deployed app.

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
- **Clean history:** the initial history was prepared locally as a single commit, with superseded local commits and objects pruned (`git fsck` reported no unreachable objects) before it was published. Later changes are new commits on top; the published commit is never amended or rewritten. Files excluded by `.gitignore` (`legacy/`, `data/source_dicom/`, `planning/`, build output) are verified ignored and absent from the commit.
- **Verification of the latest follow-up commit (development dependencies only):** 187 tracked files, 166 tests pass with no warnings (including with deprecation warnings treated as errors), consistency audit 14/14, frontend type-check and production build succeed, `npm audit --omit=dev` reports 0 runtime vulnerabilities (the full audit's 9 build/dev-only findings are listed in section 4), and `pip-audit` (app and development requirements) shows only the documented oauthlib residual. Live HTTP acceptance against the running primary app `cliniq-nexus` (v5, source folder `app-v5`) on 15 Oct 2026 passed **24/24**.
