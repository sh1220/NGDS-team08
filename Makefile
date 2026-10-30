# 현재 kubeconfig context의 클러스터에 설치한다 (팀원은 관리자에게 받은 kubeconfig-<이름>.yaml).
# 앱은 ngds(restricted), 수집기(charts/ngds-monitoring)는 홈랩 인프라 레포가 ngds-monitoring에 배포한다.
NS        ?= ngds
MON_NS    ?= ngds-monitoring
RELEASE   ?= ngds
CHART     ?= charts/ngds
# 홈랩 노드는 amd64. 평소엔 main 머지 시 CI가 빌드·배포하고, 이건 내 컴퓨터에서 직접 테스트할 때
IMAGE     ?= ghcr.io/sh1220/ngds-team08-mcp:$(shell git rev-parse --short HEAD)
TRANSPORT ?= stdio
MCP_DEV_PORT ?= 8001

export NS RELEASE CHART

.PHONY: image deploy seed up pf mcp-dev fault-oom fault-cpu fault-disk fault-lock fault-clear status down cluster-init

image:
	docker build --platform linux/amd64 -t $(IMAGE) .
	docker push $(IMAGE)

deploy:
	helm upgrade --install $(RELEASE) $(CHART) -n $(NS) --reset-values \
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
	  kubectl -n $(MON_NS) port-forward svc/prometheus 9090:9090 & \
	  kubectl -n $(MON_NS) port-forward svc/loki 3100:3100 & \
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
	kubectl -n $(MON_NS) get pods -o wide

down:
	helm uninstall $(RELEASE) -n $(NS)
	kubectl -n $(NS) delete pvc -l app.kubernetes.io/name=postgres --ignore-not-found

cluster-init:  ## (관리자) 네임스페이스·권한
	kubectl apply -f cluster/namespace-rbac.yaml
