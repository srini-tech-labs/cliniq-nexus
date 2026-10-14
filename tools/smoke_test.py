"""Smoke-test a deployed ClinIQ Nexus app over HTTPS using the caller's Databricks OAuth token.

Usage: python tools/smoke_test.py https://<app-url> [profile]
"""
import json
import subprocess
import sys
import time

import httpx

url, profile = sys.argv[1].rstrip("/"), (sys.argv[2] if len(sys.argv) > 2 else "cliniq")
token = json.loads(subprocess.run(["databricks", "auth", "token", "-p", profile], capture_output=True, text=True, check=True).stdout)["access_token"]
c = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120, follow_redirects=False)
results = []


def check(name, fn):
    t = time.time()
    try:
        detail = fn()
        results.append((True, name, detail, time.time() - t))
    except Exception as exc:
        results.append((False, name, f"{type(exc).__name__}: {exc}"[:200], time.time() - t))


def ok(r, code=200):
    assert r.status_code == code, f"HTTP {r.status_code}: {r.text[:150]}"
    return r


check("health", lambda: ok(c.get("/api/health")).json()["status"])
check("meta (warehouse mode)", lambda: (lambda m: (m["source"]["mode"], m["dataset"]["dataset_version"]))(ok(c.get("/api/meta")).json()))
check("frontend served", lambda: "ClinIQ Nexus" in ok(c.get("/")).text and "ok")
check("worklist (10 patients)", lambda: len(ok(c.get("/api/patients")).json()))
check("patient bundle CN-P003", lambda: len(ok(c.get("/api/patients/CN-P003")).json()["brief"]["items"]))
check("PDF from UC volume", lambda: len(ok(c.get("/api/patients/CN-P003/documents/CN-D003-1/file")).content))
check("cross-patient PDF denied", lambda: ok(c.get("/api/patients/CN-P001/documents/CN-D003-1/file"), 404).status_code)
check("quarantined PDF denied", lambda: ok(c.get("/api/patients/CN-P008/documents/CN-D008-3/file"), 404).status_code)
check("DICOM render", lambda: len(ok(c.get("/api/patients/CN-P001/imaging/CN-IMG001-1/image.png")).content))
check("operations + quality", lambda: sum(q["status"] == "pass" for q in ok(c.get("/api/operations")).json()["quality"]))
check("assistant structured", lambda: (lambda a: (a["mode"], len(a["claims"])))(ok(c.post("/api/patients/CN-P006/ask", json={"question": "Are there portal messages awaiting a reply?"})).json()))
check("assistant generated", lambda: (lambda a: (a["mode"], a["validation"]["level"], a["retrieval"].get("mode"), [s["label"] for s in a["sources"]][:2]))(
    ok(c.post("/api/patients/CN-P008/ask", json={"question": "Why was aspirin stopped and was the patient still taking it?"})).json()))
check("assistant scope policy", lambda: ok(c.post("/api/patients/CN-P001/ask", json={"question": "What medications is CN-P002 taking?"})).json()["route"])
check("evaluation scorecard", lambda: len(ok(c.get("/api/evaluation")).json()["metrics"]))

for passed, name, detail, secs in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:28s} {secs:5.1f}s  {detail}")
sys.exit(0 if all(r[0] for r in results) else 1)
