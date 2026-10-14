# Deployment and rollback

## Current state (14 Oct 2026)

| App | Serves | Source folder (workspace) | Data | Status |
|---|---|---|---|---|
| `cliniq-nexus` (primary) | **v5** | `/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-v5` | `cliniq_v5_stage` | Promoted and validated: HTTP acceptance 24/24 |
| `cliniq-nexus-next` (candidate) | v5 (same build) | `/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-next` | `cliniq_v5_stage` | Retained for side-by-side validation; can be stopped or deleted later to free the app slot |
| v4 rollback source | v4 Streamlit | `/Workspace/Healthcare AI Agents/ClinIQ Nexus/app` (unmodified) | `cliniq_v4_stage`, `cliniq_gold`, `cliniq_bronze` | **Rollback rehearsed**: deployed to the primary app, rendered its dashboard with data, then rolled forward to v5 |

No existing schema, table, volume or notebook was modified or deleted. v5 adds:

- the schema `healthcare.cliniq_v5_stage`, which contains the volume `raw`;
- the workspace folders `app-next`, `app-v5` and `v5_pipeline`;
- the app `cliniq-nexus-next`.

## Access model (important for portfolio use)

- Databricks Apps sits behind **Databricks single sign-on**. Requests without a session are redirected to the workspace's OAuth sign-in (HTTP 302), and API calls get HTTP 401. The acceptance suite verifies both.
- Only workspace users who are granted `CAN_USE` on the app can open it. Free Edition doesn't support anonymous or public app access, so **an external recruiter can't open the app without a Databricks account in this workspace.**
- For portfolio and recruiting use, rely on:
  - the screenshots in `docs/screenshots/` and `docs/portfolio/images/`;
  - the captioned walkthrough video `docs/portfolio/media/cliniq-nexus-demo.webm` (1 min 30 s, recorded from the primary app).
- Free Edition apps **stop automatically 24 hours** after a start or deploy. Before a live demonstration, run `databricks apps start cliniq-nexus` and allow about 1–2 minutes. On startup the app warms its caches; the first request after an idle warehouse can take 5–15 seconds while the serverless warehouse resumes.

## Runtime configuration

All configuration is in `app/app.yaml` and is supplied through environment variables. No credentials are stored in the code or the repository.

| Variable | Source | Purpose |
|---|---|---|
| `DATABRICKS_WAREHOUSE_ID` | app resource `sql-warehouse` | SQL warehouse used for patient-bound reads |
| `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` | injected by Databricks Apps | The app's own service-principal identity; never in the repo |
| `CLINIQ_SCHEMA` | `app.yaml` | `healthcare.cliniq_v5_stage` |
| `CLINIQ_DATA_MODE` / `CLINIQ_FILES_MODE` | `app.yaml` | `warehouse` / `volume` (use `local` for offline development) |
| `CLINIQ_LLM_MODEL`, `CLINIQ_LLM_FALLBACK_MODEL`, `CLINIQ_VERIFIER_MODEL`, `CLINIQ_EMBED_MODEL` | `app.yaml` | Pay-per-token Foundation Model endpoints |
| `CLINIQ_AI_ENABLED` | `app.yaml` | `false` serves evidence-only answers (no model calls) |

## Required permissions (least privilege)

Each app's service principal needs:

| Object | Privilege | How it is granted |
|---|---|---|
| Catalog `healthcare` | `USE CATALOG` | SQL `GRANT` (`tools/deploy.sh`) |
| Schema `healthcare.cliniq_v5_stage` | `USE SCHEMA`, `SELECT` | SQL `GRANT` (`tools/deploy.sh`) |
| Volume `healthcare.cliniq_v5_stage.raw` | `READ VOLUME` | App resource `v5-raw-volume` |
| SQL warehouse | `CAN_USE` | App resource `sql-warehouse` |
| `databricks-gpt-oss-120b`, `databricks-gpt-oss-20b`, `databricks-meta-llama-3-3-70b-instruct`, `databricks-gte-large-en` | `CAN_QUERY` | App resources (`tools/app_spec.template.json`) |

The primary app also keeps its original v4 resources (Gold table `SELECT` grants), so the v4 rollback source can run without any permission change.

## Foundation-model quota handling

- Pay-per-token endpoints on Free Edition are rate-limited. Ingestion embeds in batches of 8, because 16 inputs per request return HTTP 429.
- At request time the SDK retry window is capped at 20 s. Each narrative question uses at most: 1 embedding call, 1–2 generation calls (the primary model, then the fallback once if the first answer is unavailable or rejected), and 1–2 verification calls.
- If the embedding call fails, retrieval falls back to lexical (BM25) ranking.
- If generation fails, the answer degrades to **evidence only**, with the reason shown.
- Structured questions, policy responses and every non-assistant view make **no** model calls.

## 1. Data (one-off, idempotent)

```bash
python datagen/generate.py                      # writes data/v5/raw (synthetic only)
python pipeline/cliniq_pipeline.py              # optional local build + integrity checks
# Databricks: schema, volume, upload, ingestion job (writes tables only if all 14 checks pass)
databricks -p <profile> api post /api/2.0/sql/statements --json '{"warehouse_id":"<id>","statement":"CREATE SCHEMA IF NOT EXISTS healthcare.cliniq_v5_stage"}'
databricks -p <profile> api post /api/2.0/sql/statements --json '{"warehouse_id":"<id>","statement":"CREATE VOLUME IF NOT EXISTS healthcare.cliniq_v5_stage.raw"}'
databricks -p <profile> fs cp -r data/v5/raw dbfs:/Volumes/healthcare/cliniq_v5_stage/raw/v5 --overwrite
databricks -p <profile> workspace import "<folder>/v5_pipeline/cliniq_pipeline.py" --file pipeline/cliniq_pipeline.py --format AUTO --overwrite
databricks -p <profile> workspace import "<folder>/v5_pipeline/ClinIQ_Nexus_10_v5_Ingestion" --file notebooks/ClinIQ_Nexus_10_v5_Ingestion.py --format SOURCE --language PYTHON --overwrite
databricks -p <profile> jobs submit --json '{"run_name":"cliniq-v5-ingestion","tasks":[{"task_key":"ingest","notebook_task":{"notebook_path":"<folder>/v5_pipeline/ClinIQ_Nexus_10_v5_Ingestion","source":"WORKSPACE"}}]}'
```

## 2. Deploy

```bash
# candidate (creates the app on first run)
tools/deploy.sh --profile <profile> --warehouse <warehouse-id>
# primary app, from the dedicated release folder
tools/deploy.sh --profile <profile> --warehouse <warehouse-id> --app cliniq-nexus --path "<folder>/app-v5"
```

The script:

1. Builds the frontend.
2. Uploads the bundle.
3. Creates the app if it's missing, with the resources in `tools/app_spec.template.json`.
4. Grants read-only access on the v5 schema.
5. Deploys.
6. Runs `tools/smoke_test.py`.

It **refuses** to write to the v4 folder `<folder>/app`. For the full end-to-end gate, run `python tools/acceptance_http.py <app-url> <profile>` afterwards.

### Promotion performed on 14 Oct 2026

1. Snapshotted the primary app's configuration (kept locally, outside the repo) and confirmed v4 was healthy (HTTP 200, Streamlit).
2. Copied the validated bundle to the release folder `app-v5`.
3. Added the v5 app resources to `cliniq-nexus` alongside its existing v4 resources.
4. Granted the primary app's service principal `USE SCHEMA` and `SELECT` on `cliniq_v5_stage`.
5. Deployed `app-v5` to `cliniq-nexus`. Deployment succeeded and the app started.
6. HTTP acceptance on the primary app passed **24/24**: access control, runtime, all routes, all 10 patients' isolation, 22 PDFs with page identity, cross-patient denial, quarantine, 10 DICOM studies, operations, scorecard, and 9 assistant cases.
7. **Rollback rehearsal:**
   1. Deployed the v4 folder to `cliniq-nexus`.
   2. `tools/check_v4.py` confirmed the v4 dashboard rendered with data.
   3. Redeployed `app-v5` to `cliniq-nexus`.
   4. Re-ran acceptance: 24/24.

## 3. Rollback (exact procedure)

```bash
# 1. restore the v4 Streamlit app on the primary URL (about 1–2 minutes)
databricks -p <profile> apps deploy cliniq-nexus --source-code-path "/Workspace/Healthcare AI Agents/ClinIQ Nexus/app"
# 2. verify v4 renders with data
python tools/check_v4.py https://<cliniq-nexus-url> <profile>
# 3. (optional) return to v5
databricks -p <profile> apps deploy cliniq-nexus --source-code-path "/Workspace/Healthcare AI Agents/ClinIQ Nexus/app-v5"
python tools/acceptance_http.py https://<cliniq-nexus-url> <profile>
```

- No permission changes are needed for either direction, because the primary app holds both resource sets.
- The v4 data (`cliniq_v4_stage`, Gold, Bronze) has not been modified.
- A local copy of the v4 source and app configuration is kept outside the public repository.
- To remove v5 data entirely, drop only `healthcare.cliniq_v5_stage` (`CASCADE`). No other object depends on it.

## 4. Resource usage and cost

| Resource | Usage | Incremental paid cost |
|---|---|---|
| Apps | `cliniq-nexus` (existing) + `cliniq-nexus-next` (candidate) | $0 (Free Edition app slots) |
| SQL warehouse | Existing 2X-Small serverless warehouse; parameterized reads; 15-minute in-app cache | $0 |
| Serverless jobs | One ingestion run of about 3 minutes per data refresh | $0 |
| Foundation Model APIs | Pay-per-token endpoints within Free Edition quota; model calls only for narrative questions | $0 |
| Storage | ~8 MB volume and ~3 MB Delta | $0 |

No warehouses, Vector Search endpoints, provisioned-throughput endpoints or external services were created.
