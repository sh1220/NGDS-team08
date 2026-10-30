# Installs into the cluster of the current kubeconfig context (no cluster is created).
NS        ?= semantic-obs
RELEASE   ?= semantic-obs
CHART     ?= helm/semantic-obs
# must be pullable by the target cluster, e.g. ghcr.io/<you>/semantic-obs-mcp:0.1.0
IMAGE     ?= semantic-obs-mcp:dev
TRANSPORT ?= stdio
MCP_DEV_PORT ?= 8001

export NS RELEASE CHART

.PHONY: image deploy seed up pf mcp-dev fault-oom fault-cpu fault-disk fault-lock fault-clear status down

image:
	docker build -t $(IMAGE) .
	docker push $(IMAGE)

deploy:
	helm upgrade --install $(RELEASE) $(CHART) -n $(NS) --create-namespace --reset-values \
	  --set mcp.image=$(IMAGE) --wait --timeout 10m

seed:
	@kubectl -n $(NS) port-forward svc/neo4j 7687:7687 >/dev/null 2>&1 & PF=$$!; \
	  trap "kill $$PF" EXIT; \
	  for i in $$(seq 1 30); do nc -z localhost 7687 2>/dev/null && break; sleep 1; done; \
	  NEO4J_URI=bolt://localhost:7687 uv run python scripts/seed_kg.py
	./scripts/faults/_common.sh ensure_pgbench

up: deploy seed

pf:
	@echo "port-forwarding prometheus:9090 loki:3100 neo4j:7687,7474 mcp:8000 (Ctrl-C to stop)"
	@trap 'kill 0' INT TERM; \
	  kubectl -n $(NS) port-forward svc/prometheus 9090:9090 & \
	  kubectl -n $(NS) port-forward svc/loki 3100:3100 & \
	  kubectl -n $(NS) port-forward svc/neo4j 7687:7687 7474:7474 & \
	  kubectl -n $(NS) port-forward svc/mcp 8000:8000 & \
	  wait

# run the server locally against `make pf` backends: make mcp-dev [TRANSPORT=http]
mcp-dev:
	uv run python src/server.py --transport $(TRANSPORT) --port $(MCP_DEV_PORT)

fault-oom:
	./scripts/faults/oom.sh
fault-cpu:
	./scripts/faults/cpu_throttle.sh
fault-disk:
	./scripts/faults/disk_pressure.sh $(MODE)
fault-lock:
	./scripts/faults/lock_contention.sh
fault-clear:
	./scripts/faults/clear.sh

status:
	kubectl -n $(NS) get pods -o wide

down:
	helm uninstall $(RELEASE) -n $(NS)
	kubectl -n $(NS) delete pvc -l app.kubernetes.io/name=postgres --ignore-not-found
