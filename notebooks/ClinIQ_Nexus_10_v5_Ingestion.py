# Databricks notebook source
# MAGIC %md
# MAGIC # ClinIQ Nexus — v5 ingestion (synthetic data only)
# MAGIC
# MAGIC Reads the synthetic raw drop in `/Volumes/healthcare/cliniq_v5_stage/raw/v5`, extracts PDF text
# MAGIC page by page (text layer only, **no OCR**), verifies that every page's printed patient and encounter
# MAGIC identifiers match the document index (mismatches are quarantined), verifies DICOM headers against the
# MAGIC imaging catalog, builds patient-scoped retrieval chunks with page numbers, embeds them with
# MAGIC `databricks-gte-large-en`, runs integrity checks and writes curated Delta tables to
# MAGIC `healthcare.cliniq_v5_stage`. Existing ClinIQ schemas are not read or modified.

# COMMAND ----------

# MAGIC %pip install pypdf==6.19.0 pydicom==3.0.2 --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
from databricks.sdk import WorkspaceClient
from cliniq_pipeline import TABLE_SCHEMAS, coerce, process

CATALOG_SCHEMA = "healthcare.cliniq_v5_stage"
RAW = "/Volumes/healthcare/cliniq_v5_stage/raw/v5"

tables = process(RAW, embed=True, embed_client=WorkspaceClient(), expected_quarantine=1)
print({k: len(v) for k, v in tables.items()})

# COMMAND ----------

failed = [c for c in tables["integrity_checks"] if c["status"] != "pass"]
for c in tables["integrity_checks"]:
    print(c["check_id"], c["status"], c["check_name"], c["detail"][:100])
assert not failed, f"Integrity checks failed: {[c['check_id'] for c in failed]}"

# COMMAND ----------

for name, rows in tables.items():
    ddl = TABLE_SCHEMAS[name]
    df = spark.createDataFrame(coerce(rows, ddl), schema=ddl)
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{CATALOG_SCHEMA}.{name}"))
    spark.sql(f"COMMENT ON TABLE {CATALOG_SCHEMA}.{name} IS 'ClinIQ Nexus v5 — SYNTHETIC demonstration data, not for clinical use'")
    print(f"wrote {CATALOG_SCHEMA}.{name}: {len(rows)} rows")

# COMMAND ----------

display(spark.table(f"{CATALOG_SCHEMA}.integrity_checks"))
