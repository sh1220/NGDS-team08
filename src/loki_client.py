"""Minimal Loki HTTP API client (read-only)."""
import time

import httpx

from config import HTTP_TIMEOUT, LOKI_URL
from prom_client import window_seconds


def _get(path: str, params: dict) -> dict:
    r = httpx.get(f"{LOKI_URL}{path}", params=params, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"loki error {r.status_code}: {r.text.strip()}")
    return r.json()["data"]


def query_range(expr: str, window: str = "5m", limit: int = 100) -> list[dict]:
    """Log query -> newest-first [{ts, labels, line}]"""
    end_ns = time.time_ns()
    start_ns = end_ns - window_seconds(window) * 1_000_000_000
    data = _get("/loki/api/v1/query_range", {
        "query": expr, "start": start_ns, "end": end_ns, "limit": limit, "direction": "backward",
    })
    lines = []
    for stream in data["result"]:
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            lines.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts) / 1e9)),
                          "labels": {k: labels[k] for k in ("pod", "container") if k in labels},
                          "line": line})
    lines.sort(key=lambda x: x["ts"], reverse=True)
    return lines[:limit]


def count(expr: str, window: str = "5m") -> float:
    """Number of matching log lines in the last window (instant metric query)."""
    data = _get("/loki/api/v1/query", {"query": f"sum(count_over_time({expr} [{window}]))"})
    return sum(float(s["value"][1]) for s in data["result"])
