# Option memo: real de-identified DICOM for a future imaging demo

**Status:** for discussion only. Nothing has been downloaded or imported, and nothing will be without explicit approval.

## Why consider it

The current imaging objects are synthetic Secondary Capture test patterns. They show DICOM handling (header parsing, window/level, study–encounter–report linkage) honestly, but the viewer doesn't look like a radiology tool. A small set of public, de-identified studies could show multi-slice CT/MR handling and series navigation.

## Constraints any option must meet

1. **License** allows public redistribution in a portfolio repo, or at least public display, with attribution. Each collection's license must be confirmed **at the time of import**; licenses differ by collection and can change.
2. **De-identification provenance** is documented by the publisher, so no PHI exists in headers or burned-in pixels. Even so, every file must be re-checked: scan headers for PatientName, dates and institution tags, and inspect for burned-in text.
3. **Honest presentation.** Real images must **not** be attached to synthetic patients as if they were those patients' scans. That would create a false clinical narrative. The recommended form is a separate "Reference imaging library" with the source, license and attribution shown, or images clearly labelled "illustrative public image — not this patient's study".
4. **Free Edition fit:** a few series only (tens of MB), stored in a new volume, rendered server-side, with no new paid services.
5. **No AI interpretation.** The assistant still never describes pixels. Only metadata and published, attributed reports, if any exist, may be cited.

## Candidate sources (verify each before use)

| Source | Format | Access and licensing (as generally published; verify per collection) | Fit |
|---|---|---|---|
| The Cancer Imaging Archive (TCIA) | DICOM CT/MR/PET, de-identified | Many collections under Creative Commons Attribution (CC BY 3.0/4.0); some require a data-use agreement. The license is stated per collection. | **Best fit:** pick one small CC BY collection and a handful of series |
| NIH Clinical Center ChestX-ray14 | PNG (not DICOM) | Publicly released with a citation request | Poor fit: not DICOM; would need conversion and misrepresents provenance |
| RSNA challenge datasets (e.g. pneumonia detection) | DICOM | Distributed under competition or challenge terms that may restrict redistribution | Avoid unless the terms clearly allow portfolio use |
| MIDRC | DICOM | Requires registration and a data-use agreement | Not suitable for a public repository |
| `pydicom` test fixtures | DICOM | Small fixture files with mixed origins and licenses | Suitable only for unit tests, not the demo |

## Ingestion plan, if approved

1. Choose the collection and record the license URL, citation and version in `data/reference_imaging/SOURCE.md`.
2. Download a small subset outside the app, then run a header and pixel audit script: reject files with names, birth dates, institution identifiers or burned-in text.
3. Upload to a new volume `healthcare.cliniq_reference.imaging`. The v5 clinical data stays unchanged.
4. Add a `reference_imaging` table (series, modality, slice count, license, attribution) and a separate viewer route that supports series scrolling.
5. Add tests: license metadata present, no PHI tags, never linked to synthetic patients.

Estimated effort is 1–2 days. Incremental cost is $0 (storage of a few tens of MB).
