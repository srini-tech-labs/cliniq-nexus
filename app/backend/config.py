"""Runtime configuration (environment variables only; no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    warehouse_id: str = field(default_factory=lambda: _env("DATABRICKS_WAREHOUSE_ID", ""))
    data_mode: str = field(default_factory=lambda: _env("CLINIQ_DATA_MODE", "warehouse" if os.getenv("DATABRICKS_WAREHOUSE_ID") else "local"))
    schema: str = field(default_factory=lambda: _env("CLINIQ_SCHEMA", "healthcare.cliniq_v5_stage"))
    local_dir: Path = field(default_factory=lambda: Path(_env("CLINIQ_LOCAL_DIR", str(ROOT.parent / "data" / "v5"))))
    files_mode: str = field(default_factory=lambda: _env("CLINIQ_FILES_MODE", "volume" if os.getenv("DATABRICKS_WAREHOUSE_ID") else "local"))
    llm_model: str = field(default_factory=lambda: _env("CLINIQ_LLM_MODEL", "databricks-gpt-oss-120b"))
    llm_fallback_model: str = field(default_factory=lambda: _env("CLINIQ_LLM_FALLBACK_MODEL", "databricks-gpt-oss-20b"))
    verifier_model: str = field(default_factory=lambda: _env("CLINIQ_VERIFIER_MODEL", "databricks-meta-llama-3-3-70b-instruct"))
    embed_model: str = field(default_factory=lambda: _env("CLINIQ_EMBED_MODEL", "databricks-gte-large-en"))
    ai_enabled: bool = field(default_factory=lambda: _env("CLINIQ_AI_ENABLED", "true").lower() == "true")
    cache_ttl_seconds: int = field(default_factory=lambda: int(_env("CLINIQ_CACHE_TTL", "900")))
    volume_root: str = "/Volumes/healthcare/cliniq_v5_stage/raw/v5"
    static_dir: Path = ROOT / "frontend" / "dist"
    eval_results: Path = ROOT / "backend" / "eval_latest.json"


settings = Settings()
