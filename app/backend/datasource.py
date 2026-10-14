"""Read-only data access with a fixed table allowlist and enforced patient scoping.

Two interchangeable sources return identical row shapes:
  * WarehouseSource — Databricks SQL warehouse over Unity Catalog (deployed app, live dev)
  * LocalSource     — JSON produced by the same pipeline (offline tests and prototyping)

Patient-scoped reads always bind the patient identifier as a query parameter and are
re-checked after retrieval (defence in depth) before any row reaches the API or a model.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

# Tables the application may read. Values: (patient_scoped, columns or "*").
ALLOWED_TABLES: dict[str, bool] = {
    "patients": True, "encounters": True, "conditions": True, "observations": True,
    "medication_requests": True, "clinical_notes": True, "follow_up_items": True,
    "portal_threads": True, "portal_messages": True, "imaging_studies": True, "imaging_reports": True,
    "documents": True, "document_pages": True, "knowledge_chunks": True, "chunk_embeddings": True,
    "integrity_checks": False, "dataset_manifest": False, "document_quarantine": False,
}
# Columns that are never needed for directory/operational (cross-patient) reads.
TEXT_HEAVY = {"clinical_notes": "note_text", "document_pages": "page_text", "knowledge_chunks": "chunk_text",
              "portal_messages": "message_body", "imaging_reports": "report_text", "chunk_embeddings": "embedding"}
PATIENT_ID = re.compile(r"^CN-P\d{3}$")


class ScopeError(RuntimeError):
    """Raised when a row outside the requested patient scope is encountered."""


def check_patient_id(patient_id: str) -> str:
    if not isinstance(patient_id, str) or not PATIENT_ID.match(patient_id):
        raise ValueError("Invalid patient identifier")
    return patient_id


class _TTLCache:
    def __init__(self, ttl: int):
        self.ttl, self._data, self._lock = ttl, {}, threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return hit[1]
        return None

    def put(self, key, value):
        with self._lock:
            self._data[key] = (time.monotonic(), value)

    def clear(self):
        with self._lock:
            self._data.clear()


class BaseSource:
    mode = "base"

    def __init__(self):
        self.cache = _TTLCache(settings.cache_ttl_seconds)

    # ---- implemented by subclasses
    def _fetch(self, table: str, patient_id: str | None, columns: list[str] | None) -> list[dict]:
        raise NotImplementedError

    # ---- public API
    def patient_rows(self, table: str, patient_id: str) -> list[dict]:
        if not ALLOWED_TABLES.get(table):
            raise ValueError(f"Table not allowed for patient-scoped read: {table}")
        check_patient_id(patient_id)
        key = ("p", table, patient_id)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = self._fetch(table, patient_id, None)
        for r in rows:
            if r.get("patient_id") != patient_id:
                raise ScopeError(f"{table}: row outside patient scope")
            if r.get("is_synthetic") is not True:
                raise ScopeError(f"{table}: non-synthetic row rejected")
        self.cache.put(key, rows)
        return rows

    def directory_rows(self, table: str) -> list[dict]:
        """Cross-patient read for the worklist and operations views (no free text)."""
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Table not allowed: {table}")
        key = ("d", table)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = self._fetch(table, None, None)
        drop = TEXT_HEAVY.get(table)
        if drop:
            rows = [{k: v for k, v in r.items() if k != drop} for r in rows]
        if ALLOWED_TABLES[table] and any(r.get("is_synthetic") is not True for r in rows):
            raise ScopeError(f"{table}: non-synthetic row rejected")
        self.cache.put(key, rows)
        return rows

    def status(self) -> dict:
        return {"mode": self.mode}


class LocalSource(BaseSource):
    mode = "local"

    def __init__(self, root: Path | None = None):
        super().__init__()
        self.root = Path(root or settings.local_dir) / "processed"
        self._tables: dict[str, list[dict]] = {}

    def _load(self, table: str) -> list[dict]:
        if table not in self._tables:
            path = self.root / f"{table}.json"
            self._tables[table] = json.loads(path.read_text()) if path.exists() else []
        return self._tables[table]

    def _fetch(self, table, patient_id, columns):
        rows = self._load(table)
        if patient_id is not None:
            rows = [r for r in rows if r.get("patient_id") == patient_id]
        return [dict(r) for r in rows]


class WarehouseSource(BaseSource):
    mode = "warehouse"

    def __init__(self, pool_size: int = 4):
        super().__init__()
        from databricks.sdk.core import Config

        self.cfg = Config()
        if not re.fullmatch(r"[A-Za-z0-9]+", settings.warehouse_id or ""):
            raise RuntimeError("DATABRICKS_WAREHOUSE_ID is not configured (app resource key: sql-warehouse)")
        self.http_path = f"/sql/1.0/warehouses/{settings.warehouse_id}"
        self.pool: queue.LifoQueue = queue.LifoQueue(maxsize=pool_size)
        self.pool_size = pool_size
        self._created = 0
        self._lock = threading.Lock()

    def _connect(self):
        from databricks import sql

        host = self.cfg.host.removeprefix("https://").removeprefix("http://")
        return sql.connect(server_hostname=host, http_path=self.http_path, credentials_provider=lambda: self.cfg.authenticate)

    def _acquire(self):
        try:
            return self.pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._created < self.pool_size:
                    self._created += 1
                    try:
                        return self._connect()
                    except Exception:
                        self._created -= 1
                        raise
            return self.pool.get(timeout=60)

    def _release(self, conn, broken: bool):
        if broken:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created -= 1
        else:
            self.pool.put(conn)

    def query(self, statement: str, params: dict[str, Any] | None = None) -> list[dict]:
        for attempt in range(2):
            conn = self._acquire()
            try:
                with conn.cursor() as cur:
                    cur.execute(statement, parameters=params or {})
                    names = [c[0] for c in cur.description]
                    rows = [dict(zip(names, row)) for row in cur.fetchall()]
                self._release(conn, broken=False)
                return [_plain(r) for r in rows]
            except Exception:
                self._release(conn, broken=True)
                if attempt == 1:
                    raise
        return []

    def _fetch(self, table, patient_id, columns):
        fq = f"{settings.schema}.{table}"            # identifier comes from the constant allowlist only
        # Identifier comes only from ALLOWED_TABLES (validated by the caller); values are bound parameters.
        if patient_id is None:
            return self.query(f"SELECT * FROM {fq}")  # nosec B608
        return self.query(f"SELECT * FROM {fq} WHERE patient_id = :pid AND is_synthetic = true", {"pid": patient_id})  # nosec B608

    def status(self) -> dict:
        return {"mode": self.mode, "schema": settings.schema, "warehouse_id": settings.warehouse_id}


def _plain(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k == "embedding" and isinstance(v, str):      # ARRAY<FLOAT> arrives as JSON text without pyarrow
            v = [float(x) for x in json.loads(v)]
        elif hasattr(v, "tolist"):
            v = v.tolist()
        elif isinstance(v, (list, tuple)):
            v = [float(x) if hasattr(x, "__float__") and not isinstance(x, (str, bool)) else x for x in v]
        out[k] = v
    return out


_source: BaseSource | None = None


def get_source() -> BaseSource:
    global _source
    if _source is None:
        _source = WarehouseSource() if settings.data_mode == "warehouse" else LocalSource()
    return _source


def set_source(source: BaseSource) -> None:
    global _source
    _source = source
