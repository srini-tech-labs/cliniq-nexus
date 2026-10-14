"""ClinIQ Nexus API and static frontend host (Databricks Apps entry point)."""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import clinical, files
from .assistant import service as assistant
from .config import settings
from .datasource import ScopeError, check_patient_id, get_source

log = logging.getLogger("cliniq")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for noisy in ("databricks.sql", "databricks.sdk", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

STARTED = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="ClinIQ Nexus", version="5.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(ScopeError)
async def scope_error(_: Request, exc: ScopeError):
    log.error("Patient scope violation blocked: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Patient-scope safeguard blocked this response."})


def _pid(patient_id: str) -> str:
    try:
        return check_patient_id(patient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient identifier")


def _warm():
    """Resume the warehouse and pre-load read models so first clicks are fast."""
    try:
        rows = clinical.worklist()
        clinical.operations()
        for r in rows:
            clinical.patient_bundle(r["patient_id"])
            get_source().patient_rows("knowledge_chunks", r["patient_id"])
            get_source().patient_rows("chunk_embeddings", r["patient_id"])
        log.info("Warm-up complete for %d patients", len(rows))
    except Exception as exc:  # warehouse may be resuming; requests will retry on demand
        log.warning("Warm-up failed: %s", exc)


# ----------------------------------------------------------------------------- meta

@app.get("/api/health")
def health():
    return {"status": "ok", "uptime_s": int(time.time() - STARTED)}


@app.get("/api/meta")
def meta():
    try:
        manifest = clinical.manifest()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Data source unavailable: {type(exc).__name__}")
    return {"dataset": manifest, "source": get_source().status(), "ai_enabled": settings.ai_enabled,
            "models": {"generator": settings.llm_model, "fallback": settings.llm_fallback_model,
                       "verifier": settings.verifier_model, "embedding": settings.embed_model},
            "synthetic": True}


@app.get("/api/patients")
def patients():
    return clinical.worklist()


@app.get("/api/patients/{patient_id}")
def patient(patient_id: str):
    try:
        return clinical.patient_bundle(_pid(patient_id))
    except LookupError:
        raise HTTPException(status_code=404, detail="Patient not found")


@app.get("/api/patients/{patient_id}/documents/{document_id}/pages")
def document_pages(patient_id: str, document_id: str):
    pid = _pid(patient_id)
    pages = [p for p in get_source().patient_rows("document_pages", pid) if p["document_id"] == document_id]
    if not pages:
        raise HTTPException(status_code=404, detail="Document not found for this patient")
    return sorted(pages, key=lambda p: p["page_number"])


@app.get("/api/patients/{patient_id}/documents/{document_id}/file")
def document_file(patient_id: str, document_id: str):
    try:
        data, doc = files.document_bytes(_pid(patient_id), document_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Document not found for this patient")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Document storage unavailable: {type(exc).__name__}")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc["file_name"]}"', "Cache-Control": "private, max-age=600"})


@app.get("/api/patients/{patient_id}/imaging/{study_id}/metadata")
def imaging_metadata(patient_id: str, study_id: str):
    try:
        return files.dicom_metadata(_pid(patient_id), study_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Study not found for this patient")
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Imaging storage unavailable: {type(exc).__name__}")


@app.get("/api/patients/{patient_id}/imaging/{study_id}/image.png")
def imaging_png(patient_id: str, study_id: str, wc: float | None = Query(None), ww: float | None = Query(None, gt=0)):
    try:
        png = files.dicom_png(_pid(patient_id), study_id, wc, ww)
    except LookupError:
        raise HTTPException(status_code=404, detail="Study not found for this patient")
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Imaging storage unavailable: {type(exc).__name__}")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/api/patients/{patient_id}/ask")
def ask(patient_id: str, body: Ask):
    try:
        result = assistant.ask(_pid(patient_id), body.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ScopeError:
        raise
    except Exception as exc:
        log.exception("Assistant failure")
        raise HTTPException(status_code=503, detail=f"Assistant temporarily unavailable ({type(exc).__name__}); no answer was generated")
    log.info("ask patient=%s route=%s mode=%s valid=%s ms=%s", result["patient_id"], result["route"], result["mode"],
             result["validation"].get("passed"), result["latency_ms"])
    return result


@app.get("/api/patients/{patient_id}/suggestions")
def suggestions(patient_id: str):
    return assistant.suggestions(_pid(patient_id))


@app.get("/api/operations")
def operations():
    return clinical.operations()


@app.get("/api/evaluation")
def evaluation():
    if settings.eval_results.exists():
        return json.loads(settings.eval_results.read_text())
    return {"available": False}


# ----------------------------------------------------------------------------- frontend

if settings.static_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (settings.static_dir / path).resolve()
        if path and candidate.is_file() and settings.static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(settings.static_dir / "index.html", headers={"Cache-Control": "no-cache"})
