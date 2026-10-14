"""Generate the ClinIQ Nexus v5 synthetic raw dataset.

Usage:  python datagen/generate.py [--out data/v5/raw]

Outputs (all synthetic):
  fhir/<table>.ndjson   flattened FHIR-style resources
  documents/*.pdf       clinical PDFs (text-layer and scanned image-only)
  dicom/*.dcm           secondary-capture test patterns
  manifest.json         dataset version, as-of date and file checksums
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build import build_all  # noqa: E402
from dicoms import write_study  # noqa: E402
from pdfs import render_documents  # noqa: E402
from scenarios import AS_OF, PATIENTS  # noqa: E402

DATASET_VERSION = "v5.0.0"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "v5", "raw"))
    out = os.path.abspath(ap.parse_args().out)
    for sub in ("fhir", "documents", "dicom"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    recs = build_all()

    patients = {p["patient_id"]: p for p in recs["patients"]}
    for study in recs["imaging_studies"]:
        info = write_study(study, patients[study["patient_id"]], os.path.join(out, "dicom", f"{study['study_id']}.dcm"))
        study.update(study_uid=info["study_uid"], sop_uid=info["sop_uid"], rows=info["rows"], columns=info["columns"])

    render_documents(PATIENTS, recs, os.path.join(out, "documents"))

    for name, rows in recs.items():
        with open(os.path.join(out, "fhir", f"{name}.ndjson"), "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")

    files = {}
    for root, _, names in os.walk(out):
        for n in sorted(names):
            if n == "manifest.json":
                continue
            full = os.path.join(root, n)
            files[os.path.relpath(full, out)] = {"sha256": sha256(full), "bytes": os.path.getsize(full)}
    manifest = {"dataset_version": DATASET_VERSION, "as_of": AS_OF, "synthetic": True,
                "generator": "datagen/generate.py", "counts": {k: len(v) for k, v in recs.items()}, "files": files}
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
