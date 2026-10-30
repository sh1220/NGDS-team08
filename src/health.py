"""check_health: run fixed probes and mark each ok|warn|anomaly against its threshold. No scoring."""
from concurrent.futures import ThreadPoolExecutor

import catalog
import loki_client
import prom_client

RANK = {"anomaly": 2, "warn": 1, "ok": 0}
LAYERS = ["node", "kubernetes", "container", "application"]


def judge(value: float | None, threshold: dict) -> str:
    if value is None:
        return "ok"
    breached = (lambda t: value > t) if threshold["op"] == ">" else (lambda t: value < t)
    if breached(threshold["anomaly"]):
        return "anomaly"
    if breached(threshold["warn"]):
        return "warn"
    return "ok"


def run_probe(probe: dict, window: str, namespace: str | None, pod: str | None) -> dict:
    threshold = probe["threshold"]
    row = {"probe": probe["id"], "layer": probe["layer"], "title": probe["title"],
           "threshold": threshold, "enters_node": probe["enters_node"]}
    try:
        if "metric" in probe:
            expr = catalog.render(catalog.metrics()[probe["metric"]]["promql"], namespace, pod, window)
            vals = [s["value"] for s in prom_client.query(expr) if s["value"] is not None]
            value = (max if threshold["op"] == ">" else min)(vals) if vals else None
        else:
            expr = catalog.render(catalog.log_queries()[probe["log"]]["logql"], namespace, pod, window)
            value = loki_client.count(expr, window)
        row.update(query=expr, value=value, status=judge(value, threshold))
        if value is None:
            row["note"] = "no data"
    except Exception as e:  # an unobservable probe is surfaced, not hidden
        row.update(status="warn", error=str(e))
    return row


def check_health(window: str = "5m", namespace: str | None = None, pod: str | None = None) -> dict:
    probes = catalog.health_probes()
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda p: run_probe(p, window, namespace, pod), probes))
    attention = sorted((r for r in rows if r["status"] != "ok"), key=lambda r: RANK[r["status"]], reverse=True)
    return {
        "window": window,
        "summary": {s: sum(r["status"] == s for r in rows) for s in ("anomaly", "warn", "ok")},
        "attention": [{k: r[k] for k in ("status", "layer", "probe", "value", "enters_node", "error") if k in r}
                      for r in attention],
        "layers": {layer: [r for r in rows if r["layer"] == layer] for layer in LAYERS},
        "_next": "For EVERY attention row call get_diagnosis(node_id=<enters_node>)."
        if attention else "All probes ok. Diagnose only if the user reports a specific symptom.",
    }
