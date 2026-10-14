"""Patient-checked access to PDFs and DICOM objects in the v5 Unity Catalog volume."""
from __future__ import annotations

import io
import threading
from functools import lru_cache

from .config import settings
from .datasource import get_source

_lock = threading.Lock()


def _read_volume(path: str) -> bytes:
    if not path.startswith(settings.volume_root + "/"):
        raise PermissionError("Path outside the approved synthetic volume")
    if settings.files_mode == "local":
        rel = path[len(settings.volume_root) + 1:]
        return (settings.local_dir / "raw" / rel).read_bytes()
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient().files.download(path).contents.read()


@lru_cache(maxsize=64)
def _cached(path: str) -> bytes:
    with _lock:
        return _read_volume(path)


def document_bytes(patient_id: str, document_id: str) -> tuple[bytes, dict]:
    doc = next((d for d in get_source().patient_rows("documents", patient_id) if d["document_id"] == document_id), None)
    if doc is None:
        raise LookupError("Document not found for this patient")
    return _cached(doc["file_path"]), doc


def study_record(patient_id: str, study_id: str) -> dict:
    study = next((s for s in get_source().patient_rows("imaging_studies", patient_id) if s["study_id"] == study_id), None)
    if study is None:
        raise LookupError("Imaging study not found for this patient")
    return study


@lru_cache(maxsize=32)
def _dicom(path: str):
    import pydicom

    return pydicom.dcmread(io.BytesIO(_cached(path)))


def dicom_metadata(patient_id: str, study_id: str) -> dict:
    study = study_record(patient_id, study_id)
    ds = _dicom(study["dicom_path"])
    if ds.PatientID != patient_id:
        raise PermissionError("DICOM header patient does not match the selected patient")
    return {
        "study_id": study_id, "sop_class": "Secondary Capture Image Storage", "modality": ds.Modality,
        "conversion_type": getattr(ds, "ConversionType", ""), "rows": int(ds.Rows), "columns": int(ds.Columns),
        "bits_stored": int(ds.BitsStored), "photometric": ds.PhotometricInterpretation,
        "study_date": ds.StudyDate, "accession": ds.AccessionNumber, "institution": getattr(ds, "InstitutionName", ""),
        "burned_in_annotation": getattr(ds, "BurnedInAnnotation", ""), "study_description": ds.StudyDescription,
        "image_comments": getattr(ds, "ImageComments", ""), "study_uid": ds.StudyInstanceUID, "sop_uid": ds.SOPInstanceUID,
        "window_center": float(ds.WindowCenter), "window_width": float(ds.WindowWidth),
    }


def dicom_png(patient_id: str, study_id: str, center: float | None, width: float | None) -> bytes:
    import numpy as np
    from PIL import Image

    study = study_record(patient_id, study_id)
    ds = _dicom(study["dicom_path"])
    if ds.PatientID != patient_id:
        raise PermissionError("DICOM header patient does not match the selected patient")
    px = ds.pixel_array.astype("float32")
    if px.ndim != 2:
        raise ValueError("Only single-frame monochrome objects are supported")
    c = float(center if center is not None else ds.WindowCenter)
    w = max(float(width if width is not None else ds.WindowWidth), 1.0)
    lo, hi = c - w / 2, c + w / 2
    img = np.clip((px - lo) / (hi - lo), 0, 1) * 255
    buf = io.BytesIO()
    Image.fromarray(img.astype("uint8"), "L").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
