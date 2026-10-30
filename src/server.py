"""Semantic Observability MCP server (read-only RCA tools)."""
import argparse
import asyncio
import json

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import catalog
import health
import loki_client
import neo4j_client
import prom_client

INSTRUCTIONS = """\
Root-cause analysis for a PostgreSQL app on Kubernetes, across layers
node -> kubernetes -> container -> application. Follow this order strictly:

STEP 1  check_health  — narrow down which layer/probe is abnormal. Read the
        worst-first `attention` list; each row names an `enters_node`.
STEP 2  get_diagnosis — for EVERY attention row, call get_diagnosis(node_id=<enters_node>)
        and walk the causal knowledge graph (Neo4j). Follow `branches` (symptom -> cause)
        using each branch's `_next_step`, and look at `parents` for upstream effects.
        Build a causal hypothesis from the graph, not from intuition.
STEP 3  query_promql / query_logql — pull ONLY the metric_id/query_id the graph pointed to
        (pass diagnosis_node=<node you came from>). Results are raw time series: judge
        yourself whether there is a spike, sustained level or trend change (the node's
        `gate` is only a reference value). Descend while the evidence holds; stop at a
        terminal node.

Do not diagnose from scores or raw data alone: the KG provides the causal evidence.
Final answer: root-cause layer, root-cause node, the causal chain walked, and the
metric/log values that confirmed each hop. Use list_* tools to discover valid ids.
run_promql/run_logql are for ad-hoc confirmation only.
"""

mcp = FastMCP("semantic-observability", instructions=INSTRUCTIONS)


@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


# ---------- STEP 1 ----------

@mcp.tool
async def check_health(window: str = "5m", namespace: str | None = None, pod: str | None = None) -> dict:
    """STEP 1. Run every fixed health probe (per layer) and judge ok|warn|anomaly against thresholds.
    Returns per-layer probes plus a worst-first `attention` list; each row has `enters_node`
    (the KG node to start get_diagnosis from). No scores."""
    return await asyncio.to_thread(health.check_health, window, namespace, pod)


# ---------- STEP 2 ----------

def _node(props: dict) -> dict:
    n = dict(props)
    if isinstance(n.get("gate"), str):
        n["gate"] = json.loads(n["gate"])
    return n


def _next_step(from_id: str, target: dict) -> str:
    gate = target.get("gate") or {}
    if "metric" in gate:
        q = f"query_promql(metric_id='{gate['metric']}', diagnosis_node='{from_id}')"
    elif "log" in gate:
        q = f"query_logql(query_id='{gate['log']}')"
    else:
        return f"get_diagnosis(node_id='{target['id']}')"
    return (f"{q} -> judge the series (reference gate {gate['op']} {gate['anomaly']}); "
            f"if abnormal -> get_diagnosis(node_id='{target['id']}')")


CY_SUMMARY = """
MATCH (n:DiagNode)
OPTIONAL MATCH (n)-[b:BRANCHES_TO]->()
RETURN n.id AS id, n.title AS title, n.layer AS layer, n.gate AS gate,
       n.entry AS entry, n.terminal AS terminal, count(b) AS branches
ORDER BY n.entry DESC, n.layer, n.id"""

CY_BY_SYMPTOM = """
MATCH (n:DiagNode {entry: true})
WHERE toLower(n.title) CONTAINS toLower($s) OR toLower(n.id) CONTAINS toLower($s)
   OR any(x IN n.symptoms WHERE toLower(x) CONTAINS toLower($s))
RETURN n {.id, .title, .layer, .gate, .symptoms} AS node"""

CY_BY_METRIC = """
OPTIONAL MATCH (:Metric {id: $m})-[:ENTERS]->(e:DiagNode)
WITH collect(e {.id, .title, .layer, .gate}) AS entries
OPTIONAL MATCH (c:DiagNode) WHERE $m IN c.metrics OR $m IN c.logs
RETURN entries, collect(c {.id, .title, .layer, .gate}) AS checked_by"""

CY_NODE = """
MATCH (n:DiagNode {id: $id})
OPTIONAL MATCH (n)-[b:BRANCHES_TO]->(c:DiagNode)
WITH n, collect(CASE WHEN c IS NULL THEN NULL ELSE
     {when: b.when, node: c {.id, .title, .layer, .gate, .metrics, .logs, .terminal}} END) AS branches
OPTIONAL MATCH (p:DiagNode)-[pb:BRANCHES_TO]->(n)
WITH n, branches, collect(CASE WHEN p IS NULL THEN NULL ELSE
     {when: pb.when, node: p {.id, .title, .layer}} END) AS parents
OPTIONAL MATCH path = (n)-[:BRANCHES_TO*1..6]->(r:DiagNode {terminal: true})
RETURN n {.*} AS node, branches, parents,
       collect(DISTINCT [x IN nodes(path) | x.id]) AS paths_to_root_causes"""


def _diagnosis(node_id: str | None, symptom: str | None, metric_id: str | None) -> dict:
    if node_id:
        rows = neo4j_client.read(CY_NODE, id=node_id)
        if not rows:
            return {"error": f"unknown node_id {node_id!r}; call list_diagnostic_nodes()"}
        r = rows[0]
        node = _node(r["node"])
        branches = []
        for b in r["branches"]:
            target = _node(b["node"])
            branches.append({"when": b["when"], "to": target, "_next_step": _next_step(node_id, target)})
        return {
            "node": node,
            "branches": branches,
            "parents": r["parents"],
            "paths_to_root_causes": [p for p in r["paths_to_root_causes"] if p],
            "_hint": "Terminal node: this is a root cause; confirm with its metrics and report."
            if node.get("terminal") else "Follow each branch's _next_step; descend into the abnormal ones.",
            "_cypher": CY_NODE.strip(),
        }
    if symptom:
        rows = neo4j_client.read(CY_BY_SYMPTOM, s=symptom)
        return {"symptom": symptom, "entry_nodes": [_node(r["node"]) for r in rows], "_cypher": CY_BY_SYMPTOM.strip()}
    if metric_id:
        r = neo4j_client.read(CY_BY_METRIC, m=metric_id)[0]
        return {"metric_id": metric_id,
                "entry_nodes": [_node(n) for n in r["entries"]],
                "checked_by": [_node(n) for n in r["checked_by"]],
                "_cypher": CY_BY_METRIC.strip()}
    rows = neo4j_client.read(CY_SUMMARY)
    for row in rows:
        row["gate"] = json.loads(row["gate"]) if row["gate"] else None
    return {"entry_nodes": [r["id"] for r in rows if r["entry"]], "nodes": rows, "_cypher": CY_SUMMARY.strip()}


@mcp.tool
async def get_diagnosis(node_id: str | None = None, symptom: str | None = None, metric_id: str | None = None) -> dict:
    """STEP 2. Traverse the causal knowledge graph in Neo4j (Cypher).
    - no args: entry nodes + summary of all nodes
    - symptom=... or metric_id=...: entry nodes that symptom/metric leads into
    - node_id=...: full node (gate, note, action, terminal) + branches (symptom->cause edges,
      each with `_next_step`: which metric to query and which gate to compare) + parents."""
    return await asyncio.to_thread(_diagnosis, node_id, symptom, metric_id)


# ---------- STEP 3 ----------

def _query_promql(metric_id, window, namespace, pod, diagnosis_node):
    m = catalog.metrics().get(metric_id)
    if not m:
        return {"error": f"unknown metric_id {metric_id!r}; call list_metrics()"}
    expr = catalog.render(m["promql"], namespace, pod, window)
    series = prom_client.query_range(expr, window)
    return {"metric_id": metric_id, "name": m["name"], "layer": m["layer"], "unit": m.get("unit"),
            "diagnosis_node": diagnosis_node, "promql": expr,
            "series": series, "note": None if series else "no series returned"}


@mcp.tool
async def query_promql(metric_id: str, window: str = "5m", namespace: str | None = None,
                       pod: str | None = None, diagnosis_node: str | None = None) -> dict:
    """STEP 3. Run a catalog PromQL template (placeholders filled) as a range query.
    Returns the PromQL used and the raw series; judge spikes/trends yourself."""
    return await asyncio.to_thread(_query_promql, metric_id, window, namespace, pod, diagnosis_node)


def _query_logql(query_id, window, namespace, pod, limit):
    q = catalog.log_queries().get(query_id)
    if not q:
        return {"error": f"unknown query_id {query_id!r}; call list_log_queries()"}
    expr = catalog.render(q["logql"], namespace, pod, window)
    lines = loki_client.query_range(expr, window, limit)
    return {"query_id": query_id, "name": q["name"], "logql": expr, "count": len(lines), "lines": lines}


@mcp.tool
async def query_logql(query_id: str, window: str = "5m", namespace: str | None = None,
                      pod: str | None = None, limit: int = 100) -> dict:
    """STEP 3. Run a catalog LogQL template against Loki. Returns the LogQL used and matching lines (newest first)."""
    return await asyncio.to_thread(_query_logql, query_id, window, namespace, pod, limit)


@mcp.tool
async def run_promql(expr: str, window: str | None = None) -> dict:
    """Ad-hoc read-only PromQL. Instant query, or range query over `window` (e.g. '5m') if given."""
    if window:
        return {"promql": expr, "series": await asyncio.to_thread(prom_client.query_range, expr, window)}
    return {"promql": expr, "result": await asyncio.to_thread(prom_client.query, expr)}


@mcp.tool
async def run_logql(expr: str, window: str = "5m", limit: int = 100) -> dict:
    """Ad-hoc read-only LogQL log query over the last `window`."""
    return {"logql": expr, "lines": await asyncio.to_thread(loki_client.query_range, expr, window, limit)}


# ---------- discovery ----------

@mcp.tool
def list_metrics() -> list[dict]:
    """Catalog metric ids (for query_promql) with layer and unit."""
    return [{k: m.get(k) for k in ("id", "layer", "name", "unit")} for m in catalog.metrics().values()]


@mcp.tool
def list_log_queries() -> list[dict]:
    """Catalog log query ids (for query_logql)."""
    return [{"id": q["id"], "layer": q["layer"], "name": q["name"]} for q in catalog.log_queries().values()]


@mcp.tool
async def list_diagnostic_nodes() -> list[dict]:
    """All KG diagnostic node ids (for get_diagnosis) with layer, entry and terminal flags."""
    rows = await asyncio.to_thread(neo4j_client.read, CY_SUMMARY)
    return [{k: r[k] for k in ("id", "title", "layer", "entry", "terminal")} for r in rows]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="http", host=args.host, port=args.port)
