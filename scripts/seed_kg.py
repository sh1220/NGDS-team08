"""Load catalog/kg/ontology.yaml into Neo4j (wipe + MERGE). Validates ids against the catalog."""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import catalog  # noqa: E402
from config import CATALOG_DIR  # noqa: E402
from neo4j_client import driver  # noqa: E402


def validate(nodes: list[dict]) -> None:
    ids = {n["id"] for n in nodes}
    metrics, logs = catalog.metrics(), catalog.log_queries()
    errors = []
    for n in nodes:
        gate = n.get("gate", {})
        for m in n.get("metrics", []) + ([gate["metric"]] if "metric" in gate else []):
            if m not in metrics:
                errors.append(f"{n['id']}: unknown metric {m}")
        for q in n.get("logs", []) + ([gate["log"]] if "log" in gate else []):
            if q not in logs:
                errors.append(f"{n['id']}: unknown log query {q}")
        for b in n.get("branches", []):
            if b["to"] not in ids:
                errors.append(f"{n['id']}: branch to unknown node {b['to']}")
    for p in catalog.health_probes():
        if p["enters_node"] not in ids:
            errors.append(f"probe {p['id']}: enters unknown node {p['enters_node']}")
    if errors:
        sys.exit("ontology validation failed:\n  " + "\n  ".join(errors))


def seed() -> None:
    nodes = yaml.safe_load((CATALOG_DIR / "kg" / "ontology.yaml").read_text())["nodes"]
    validate(nodes)
    metrics, logs = catalog.metrics(), catalog.log_queries()
    d = driver()
    d.execute_query("CREATE CONSTRAINT diag_id IF NOT EXISTS FOR (n:DiagNode) REQUIRE n.id IS UNIQUE")
    d.execute_query("CREATE CONSTRAINT metric_id IF NOT EXISTS FOR (m:Metric) REQUIRE m.id IS UNIQUE")
    d.execute_query("MATCH (n) WHERE n:DiagNode OR n:Metric DETACH DELETE n")

    for n in nodes:
        d.execute_query(
            """MERGE (d:DiagNode {id: $id})
               SET d.title = $title, d.layer = $layer, d.gate = $gate, d.metrics = $metrics,
                   d.logs = $logs, d.action = $action, d.terminal = $terminal, d.note = $note,
                   d.entry = $entry, d.symptoms = $symptoms""",
            id=n["id"], title=n["title"], layer=n["layer"],
            gate=json.dumps(n["gate"]) if n.get("gate") else None,
            metrics=n.get("metrics", []), logs=n.get("logs", []), action=n.get("action"),
            terminal=bool(n.get("terminal")), note=(n.get("note") or "").strip(),
            entry=bool(n.get("entry")), symptoms=n.get("symptoms", []),
        )

    for n in nodes:
        for b in n.get("branches", []):
            d.execute_query(
                """MATCH (a:DiagNode {id: $a}), (b:DiagNode {id: $b})
                   MERGE (a)-[r:BRANCHES_TO]->(b) SET r.when = $when""",
                a=n["id"], b=b["to"], when=b["when"],
            )

    # metric -> entry index: every signal an entry node checks, plus every health probe's signal
    enters = set()
    for n in nodes:
        if n.get("entry"):
            gate = n.get("gate", {})
            for sig in n.get("metrics", []) + n.get("logs", []) + [gate.get("metric"), gate.get("log")]:
                if sig:
                    enters.add((sig, n["id"]))
    for p in catalog.health_probes():
        enters.add((p.get("metric") or p["log"], p["enters_node"]))
    for sig, node_id in sorted(enters):
        meta = metrics.get(sig) or logs[sig]
        d.execute_query(
            """MERGE (m:Metric {id: $sig}) SET m.layer = $layer, m.kind = $kind
               WITH m MATCH (n:DiagNode {id: $node}) MERGE (m)-[:ENTERS]->(n)""",
            sig=sig, layer=meta["layer"], kind="metric" if sig in metrics else "log", node=node_id,
        )
        # entry flag follows the index so probe targets are always entry points
        d.execute_query("MATCH (n:DiagNode {id: $node}) SET n.entry = true", node=node_id)

    counts, _, _ = d.execute_query(
        "MATCH (n:DiagNode) WITH count(n) AS nodes "
        "MATCH ()-[b:BRANCHES_TO]->() WITH nodes, count(b) AS branches "
        "MATCH ()-[e:ENTERS]->() RETURN nodes, branches, count(e) AS enters")
    print("seeded:", counts[0].data())


if __name__ == "__main__":
    if "--check" in sys.argv:
        validate(yaml.safe_load((CATALOG_DIR / "kg" / "ontology.yaml").read_text())["nodes"])
        print("ontology ok")
    else:
        seed()
