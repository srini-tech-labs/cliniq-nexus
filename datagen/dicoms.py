"""Synthetic DICOM Secondary Capture test patterns aligned with v5 imaging metadata.

The pixel data is a geometric test pattern with burned-in text stating that it is not a
medical image. ConversionType is SYN (synthetic image) as defined by DICOM.
"""
from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from build import ts

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SIZE = 512


def deterministic_uid(*parts: str) -> str:
    return generate_uid(entropy_srcs=["cliniq-nexus-v5", *parts])


def pattern(study_id: str, procedure: str) -> np.ndarray:
    seed = int(hashlib.sha256(study_id.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    cx, cy = SIZE / 2 + rng.uniform(-30, 30), SIZE / 2 + rng.uniform(-30, 30)
    r = np.hypot(x - cx, y - cy)
    img = 300 + 1400 * (0.5 + 0.5 * np.cos(r / (9 + rng.uniform(0, 6))))          # concentric rings
    img *= np.clip(1.15 - r / (SIZE * 0.75), 0.15, 1.0)                              # vignette
    grid = ((x.astype(int) % 64) < 2) | ((y.astype(int) % 64) < 2)
    img[grid] = 3200                                                                 # calibration grid
    img[SIZE - 48:SIZE - 16, 32:SIZE - 32] = np.linspace(0, 4000, SIZE - 64)[None, :]  # gray-scale ramp
    for _ in range(3 + int("knee" in procedure.lower())):                            # geometric blocks
        x0, y0 = rng.integers(60, SIZE - 160, size=2)
        w, h = rng.integers(40, 110, size=2)
        img[y0:y0 + h, x0:x0 + w] = rng.uniform(1800, 3600)
    canvas = Image.fromarray(np.zeros((SIZE, SIZE), dtype=np.uint8))
    d = ImageDraw.Draw(canvas)
    d.text((24, 18), "SYNTHETIC TEST PATTERN", fill=255, font=ImageFont.truetype(FONT, 22))
    d.text((24, 46), "NOT A MEDICAL IMAGE", fill=255, font=ImageFont.truetype(FONT, 18))
    d.text((24, 72), study_id, fill=255, font=ImageFont.truetype(FONT, 14))
    text = np.asarray(canvas) > 0
    img[text] = 4095
    return np.clip(img, 0, 4095).astype(np.uint16)


def write_study(study: dict, patient: dict, path: str) -> dict:
    when = ts(study["study_at"])
    meta = FileMetaDataset()
    sop_uid = deterministic_uid(study["study_id"], "sop")
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = deterministic_uid(study["study_id"], "study")
    ds.SeriesInstanceUID = deterministic_uid(study["study_id"], "series")
    ds.PatientID = patient["patient_id"]
    ds.PatientName = f"SYNTHETIC^PATIENT{patient['patient_id'][-3:]}"
    ds.PatientBirthDate = patient["birth_date"].replace("-", "")
    ds.PatientSex = "F" if patient["sex"] == "female" else "M"
    ds.StudyDate = ds.ContentDate = when.strftime("%Y%m%d")
    ds.StudyTime = ds.ContentTime = when.strftime("%H%M%S")
    ds.AccessionNumber = study["accession_number"]
    ds.StudyID = study["study_id"]
    ds.Modality = "OT"
    ds.ConversionType = "SYN"
    ds.BurnedInAnnotation = "YES"
    ds.InstitutionName = "Nexus General Hospital (fictional)"
    ds.StudyDescription = f"SYNTHETIC TEST PATTERN (order context: {study['ordered_procedure']})"[:64]
    ds.SeriesDescription = "Synthetic secondary capture"
    ds.SeriesNumber, ds.InstanceNumber = 1, 1
    ds.ImageComments = "Synthetic geometric test pattern for software demonstration. Not a medical image; not for interpretation."
    px = pattern(study["study_id"], study["ordered_procedure"])
    ds.Rows, ds.Columns = px.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    ds.WindowCenter, ds.WindowWidth = 2048, 4096
    ds.PixelData = px.tobytes()
    ds.save_as(path, enforce_file_format=True)
    return {"study_id": study["study_id"], "study_uid": ds.StudyInstanceUID, "sop_uid": sop_uid,
            "rows": int(ds.Rows), "columns": int(ds.Columns)}
