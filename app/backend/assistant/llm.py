"""Calls to Databricks Foundation Model serving endpoints (pay-per-token, no provisioned resources)."""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache


class ModelError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _client():
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config

    # Bound retries so a rate-limited endpoint degrades quickly to the documented fallback.
    return WorkspaceClient(config=Config(retry_timeout_seconds=20, http_timeout_seconds=90))


def chat(model: str, messages: list[dict], max_tokens: int = 1200, temperature: float = 0.0, timeout_s: int = 60) -> dict:
    """Return {'text', 'finish_reason', 'usage', 'latency_ms', 'model'}; raises ModelError."""
    t0 = time.monotonic()
    try:
        resp = _client().api_client.do("POST", f"/serving-endpoints/{model}/invocations",
                                       body={"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
    except Exception as exc:  # network, auth, quota
        raise ModelError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    choices = resp.get("choices") or []
    if not choices:
        raise ModelError("Model returned no choices")
    content = choices[0].get("message", {}).get("content")
    if isinstance(content, list):  # reasoning models return typed content blocks
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
    return {"text": (content or "").strip(), "finish_reason": choices[0].get("finish_reason"), "usage": resp.get("usage") or {},
            "latency_ms": int((time.monotonic() - t0) * 1000), "model": model}


def embed(model: str, text: str) -> list[float]:
    try:
        resp = _client().api_client.do("POST", f"/serving-endpoints/{model}/invocations", body={"input": [text]})
        return [float(x) for x in resp["data"][0]["embedding"]]
    except Exception as exc:
        raise ModelError(f"Embedding failed: {type(exc).__name__}") from exc


def parse_json(text: str) -> dict:
    """Extract the first JSON object from model output (tolerates code fences and trailing text)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("Unterminated JSON object in model output")
