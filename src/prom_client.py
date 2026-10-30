"""Minimal Prometheus HTTP API client (read-only)."""
import math
import time

import httpx

from config import HTTP_TIMEOUT, PROMETHEUS_URL


def window_seconds(window: str) -> int:
    return int(window[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[window[-1]]


def _get(path: str, params: dict) -> dict:
    r = httpx.get(f"{PROMETHEUS_URL}{path}", params=params, timeout=HTTP_TIMEOUT)
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"prometheus error: {body.get('error', r.text)}")
    return body["data"]


def _num(v: str) -> float | None:
    f = float(v)
    return None if math.isnan(f) or math.isinf(f) else round(f, 6)


def query(expr: str) -> list[dict]:
    """Instant query -> [{labels, value}]"""
    data = _get("/api/v1/query", {"query": expr})
    if data["resultType"] == "scalar":
        return [{"labels": {}, "value": _num(data["result"][1])}]
    return [{"labels": s["metric"], "value": _num(s["value"][1])} for s in data["result"]]


def query_range(expr: str, window: str = "5m") -> list[dict]:
    """Range query over the last `window` -> [{labels, values:[[ts, v]]}]. The AI judges spikes/trends."""
    end = time.time()
    seconds = window_seconds(window)
    step = max(15, seconds // 30)
    data = _get("/api/v1/query_range", {"query": expr, "start": end - seconds, "end": end, "step": step})
    return [{"labels": s["metric"], "values": [[int(ts), _num(v)] for ts, v in s["values"]]}
            for s in data["result"]]
