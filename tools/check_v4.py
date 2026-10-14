"""Verify the legacy v4 Streamlit app renders its data (used to rehearse rollback). Usage: python tools/check_v4.py <url> [profile] [png]"""
import glob, json, os, subprocess, sys
from playwright.sync_api import sync_playwright

url, profile = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "cliniq")
png = sys.argv[3] if len(sys.argv) > 3 else None
tok = json.loads(subprocess.run(["databricks", "auth", "token", "-p", profile], capture_output=True, text=True, check=True).stdout)["access_token"]
exe = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))[-1]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe)
    page = b.new_page(viewport={"width": 1400, "height": 900}, extra_http_headers={"Authorization": f"Bearer {tok}"})
    page.goto(url)
    page.wait_for_selector("text=Hospital operations overview", timeout=180000)
    page.wait_for_selector("text=Synthetic patients", timeout=120000)
    ok = page.get_by_text("Synthetic patients").count() > 0
    if png:
        page.screenshot(path=png)
    b.close()
print("v4 rendered dashboard with data:", ok)
sys.exit(0 if ok else 1)
