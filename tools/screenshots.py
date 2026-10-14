"""Capture product screenshots with Playwright.

Usage: python tools/screenshots.py --base http://127.0.0.1:8000 --out docs/screenshots [--only name]
"""
from __future__ import annotations

import argparse
import glob
import os
import time

from playwright.sync_api import sync_playwright

SHOTS = [
    ("01-welcome", "/", None),
    ("02-brief-heart-failure", "/patients/CN-P003", None),
    ("03-journey", "/patients/CN-P001/journey", None),
    ("04-trends", "/patients/CN-P003/trends", None),
    ("05-medications", "/patients/CN-P008/medications", None),
    ("06-communications", "/patients/CN-P006/communications", None),
    ("07-documents", "/patients/CN-P005/documents", None),
    ("08-pdf-citation", "/patients/CN-P003", "pdf"),
    ("09-assistant-generated", "/patients/CN-P008", "ask:Why was aspirin stopped and was the patient still taking it?"),
    ("10-assistant-structured", "/patients/CN-P009", "ask:Are there portal messages awaiting a reply?"),
    ("11-assistant-policy", "/patients/CN-P002", "ask:Should we increase the glargine dose?"),
    ("12-imaging", "/patients/CN-P001/imaging", None),
    ("13-operations", "/operations", None),
    ("14-how-it-works", "/about", None),
]


def chromium() -> str | None:
    found = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    return found[-1] if found else None


def settle(page, ms=1500):
    page.wait_for_load_state("networkidle")
    time.sleep(ms / 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--only", default=None)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--profile", default=None, help="Databricks CLI profile whose OAuth token is sent (for deployed apps)")
    ap.add_argument("--tablet", action="store_true", help="Also capture a 1024px tablet view of the brief")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium())
        headers = {}
        if a.profile:
            import json, subprocess
            tok = json.loads(subprocess.run(["databricks", "auth", "token", "-p", a.profile], capture_output=True, text=True, check=True).stdout)["access_token"]
            headers = {"Authorization": f"Bearer {tok}"}
        page = browser.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1.5, extra_http_headers=headers)
        for name, path, action in SHOTS:
            if a.only and a.only not in name:
                continue
            page.goto(a.base + path)
            settle(page, 2500)
            if action == "pdf":
                page.get_by_role("button", name="Discharge Summary · 3 Sep 2026").first.click()
                settle(page, 3000)
            elif action and action.startswith("ask:"):
                page.get_by_label("Question about this patient").fill(action[4:])
                page.locator("form button[type=submit]").click()
                page.wait_for_function("() => !document.querySelector('[role=status] .animate-spin')", timeout=90000)
                settle(page, 1200)
            page.screenshot(path=os.path.join(a.out, f"{name}.png"))
            print("captured", name)
        if a.tablet:
            tab = browser.new_page(viewport={"width": 1024, "height": 1366}, device_scale_factor=1.5, extra_http_headers=headers)
            tab.goto(a.base + "/patients/CN-P006")
            settle(tab, 3000)
            tab.screenshot(path=os.path.join(a.out, "15-tablet-brief.png"))
            print("captured 15-tablet-brief")
        browser.close()


if __name__ == "__main__":
    main()
