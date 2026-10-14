"""Offline test configuration: the app reads the locally built v5 pipeline output; models are stubbed."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CLINIQ_DATA_MODE", "local")
os.environ.setdefault("CLINIQ_FILES_MODE", "local")
os.environ.setdefault("CLINIQ_LOCAL_DIR", str(ROOT / "data" / "v5"))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "pipeline"))

import pytest  # noqa: E402

PATIENTS = [f"CN-P{i:03d}" for i in range(1, 11)]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if a test reaches a model endpoint without stubbing it."""
    from backend.assistant import llm

    def blocked(*a, **k):
        raise llm.ModelError("network disabled in tests")

    monkeypatch.setattr(llm, "chat", blocked)
    monkeypatch.setattr(llm, "embed", blocked)
    from backend.assistant import service
    monkeypatch.setattr(service, "chat", blocked)
    monkeypatch.setattr(service, "embed", blocked)
    yield


@pytest.fixture(scope="session")
def processed():
    import json
    d = ROOT / "data" / "v5" / "processed"
    return {p.stem: json.loads(p.read_text()) for p in d.glob("*.json")}
