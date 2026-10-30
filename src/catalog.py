"""Loads catalog YAML (metrics, log queries, health probes) and renders templates."""
import re
from functools import lru_cache

import yaml

from config import CATALOG_DIR, DATA_MOUNTPOINT, TARGET_CONTAINER, TARGET_NAMESPACE, TARGET_POD

_WINDOW_RE = re.compile(r"^\d+[smhd]$")
_LABEL_VALUE_RE = re.compile(r'^[^"\\{}]+$')


@lru_cache
def metrics() -> dict:
    out = {}
    for path in sorted((CATALOG_DIR / "metrics").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for mid, m in doc["metrics"].items():
            out[mid] = {**m, "id": mid, "layer": doc["layer"]}
    return out


@lru_cache
def log_queries() -> dict:
    out = {}
    for path in sorted((CATALOG_DIR / "logs").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for qid, q in doc["queries"].items():
            out[qid] = {**q, "id": qid, "layer": doc.get("layer", "application")}
    return out


@lru_cache
def health_probes() -> list[dict]:
    return yaml.safe_load((CATALOG_DIR / "health_probes.yaml").read_text())["probes"]


def render(template: str, namespace: str | None = None, pod: str | None = None, window: str = "5m") -> str:
    """Substitute {namespace} {pod} {container} {window} {mountpoint}. PromQL braces are left untouched."""
    if not _WINDOW_RE.match(window):
        raise ValueError(f"invalid window {window!r}; use e.g. 5m, 1h")
    values = {
        "namespace": namespace or TARGET_NAMESPACE,
        "pod": pod or TARGET_POD,
        "container": TARGET_CONTAINER,
        "window": window,
        "mountpoint": DATA_MOUNTPOINT,
    }
    for key, val in values.items():
        if not _LABEL_VALUE_RE.match(val):
            raise ValueError(f"invalid {key} value {val!r}")
        template = template.replace("{" + key + "}", val)
    return template.strip()
