"""Record the source take of the ClinIQ Nexus walkthrough (for portfolios where the app requires Databricks sign-in).

Usage: python tools/demo_video.py --base https://<app-url> --profile <cli-profile> --out build/media
Produces <name>/frames/*.png, <name>/frames.json and <name>/cues.json. Then run tools/build_walkthrough.py,
which assembles the captioned and clean deliverables and the WebVTT track from this single take.

Capture method:
* Frames come straight from the browser compositor through the DevTools screencast (lossless PNG, each with
  its own wall-clock timestamp). The page is never modified: no injected elements, overlays or repaints.
* The browser only emits a frame when the screen changes; the builder holds each frame until the next one
  and freezes the last stable frame for the closing hold, so static periods are reproduced exactly.
* Caption cues are logged against the same wall clock as the frame timestamps.
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

FINAL_HOLD_S = 5.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--profile", default="cliniq")
    ap.add_argument("--out", default="build/media")
    ap.add_argument("--name", default="walkthrough-source")
    a = ap.parse_args()
    root = Path(a.out) / a.name
    shutil.rmtree(root, ignore_errors=True)
    (root / "frames").mkdir(parents=True)
    tok = json.loads(subprocess.run(["databricks", "auth", "token", "-p", a.profile], capture_output=True, text=True, check=True).stdout)["access_token"]
    exe = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))[-1]
    frames: list[dict] = []
    cues: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                            extra_http_headers={"Authorization": f"Bearer {tok}"})
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)

        def on_frame(params):
            name = f"{len(frames):06d}.png"
            (root / "frames" / name).write_bytes(base64.b64decode(params["data"]))
            frames.append({"t": params["metadata"]["timestamp"], "file": name})
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "png", "maxWidth": 1440, "maxHeight": 900, "everyNthFrame": 1})

        def wait(seconds):
            page.wait_for_timeout(int(seconds * 1000))   # keeps the event loop pumping frames

        def cap(text, hold=3.2):
            now = time.time()
            if cues and cues[-1]["end"] is None:
                cues[-1]["end"] = now
            cues.append({"start": now, "end": None, "text": text})
            wait(hold)

        def go(path):
            page.goto(a.base + path)
            page.wait_for_load_state("networkidle")
            wait(1.2)

        go("/")
        wait(0.8)
        cap("ClinIQ Nexus — a physician-first clinical intelligence workspace on Databricks (synthetic records only).", 4)
        cap("Question it answers: what has happened with this patient, what matters, and where is the evidence?", 3.5)
        go("/patients/CN-P003")
        cap("Patient brief: items needing attention are derived deterministically from the records.", 3.5)
        cap("An unanswered portal message, a recent admission (discharged), abnormal results, an unsearchable scan.", 3.5)
        page.get_by_role("button", name="Discharge Summary · 3 Sep 2026").first.click()
        wait(2.5)
        cap("Every item links to its source — here the discharge summary PDF, read from a Unity Catalog volume.", 4)
        page.keyboard.press("Escape")
        go("/patients/CN-P003/journey")
        cap("Longitudinal journey: encounters, notes and PDFs, medication changes, results, messages and imaging.", 4)
        go("/patients/CN-P003/trends")
        cap("Trends: one chart per measure with units, LOINC codes, reference bands and the inpatient stay shaded.", 4)
        go("/patients/CN-P008/medications")
        cap("Medication history from FHIR-style orders: started, changed, stopped and inpatient-only.", 3.5)
        page.get_by_label("Question about this patient").fill("Why was aspirin stopped and was the patient still taking it?")
        page.locator("form button[type=submit]").click()
        cap("Ask the record: retrieval is limited to this patient; the answer must pass grounding checks and a second-model verifier.", 2)
        page.wait_for_function("() => !document.querySelector('[role=status] .animate-spin')", timeout=120000)
        wait(1)
        cap("Each claim cites its source — notes, PDF pages, orders — and opens the exact passage.", 3.5)
        citation = page.locator("button[title^='Open source']").first
        if citation.count():
            citation.click()
            wait(2.5)
            cap("The cited passage is highlighted in the source record.", 3.5)
            page.keyboard.press("Escape")
        page.get_by_label("Question about this patient").fill("Should we increase the apixaban dose?")
        page.locator("form button[type=submit]").click()
        page.wait_for_function("() => !document.querySelector('[role=status] .animate-spin')", timeout=120000)
        cap("Requests for recommendations are declined by policy; related documentation is listed instead.", 4)
        go("/patients/CN-P006/communications")
        cap("Care coordination: threads awaiting reply or routed without completion, with waiting time.", 4)
        go("/patients/CN-P001/imaging")
        cap("Imaging: real DICOM handling (window/level, header metadata, linked report) on synthetic test patterns — never interpreted.", 4.5)
        go("/operations")
        cap("Operations: encounter mix, documentation coverage, communication patterns and 14 live data-integrity checks.", 4)
        page.mouse.wheel(0, 900)
        wait(2)
        go("/about")
        cap("Architecture: Unity Catalog volume → serverless ingestion → Delta → SQL warehouse → FastAPI + React app → Foundation Model APIs.", 5)
        # Final disclosure: the page is static from here; the builder freezes the last stable frame for the hold.
        cues.append({"start": time.time(), "end": None, "text": "Synthetic demonstration — not a clinical decision-support system, EHR or HIPAA-validated software."})
        cues[-2]["end"] = cues[-1]["start"]
        wait(1.0)
        cues[-1]["end"] = cues[-1]["start"] + FINAL_HOLD_S
        cdp.send("Page.stopScreencast")
        ctx.close()
        b.close()
    (root / "frames.json").write_text(json.dumps(frames))
    (root / "cues.json").write_text(json.dumps(cues, indent=1))
    print(f"saved {len(frames)} lossless frames and {len(cues)} cues to {root}")


if __name__ == "__main__":
    main()
