# Semantic Observability — RCA 프로토타입

Kubernetes 위의 PostgreSQL 하나를 대상으로, node → kubernetes → container → application
계층의 메트릭·로그를 보고 **Neo4j에 저장된 인과 지식 그래프(KG)를 Cypher로 탐색**해
LLM이 장애 근본 원인을 찾도록 하는 MCP 서버.
MAPE-K 관점에서 Knowledge는 그래프로 외부화하고, Analyze는 LLM + MCP가 맡는다.

## 동작 흐름

```
STEP1 check_health   ── 고정 probe 실행 → 이상 probe를 worst-first로 (각 probe에 진입할 KG 노드 표시)
STEP2 get_diagnosis  ── Neo4j Cypher로 KG 탐색: 증상 노드 → BRANCHES_TO → 원인 노드
STEP3 query_promql / query_logql ── KG가 가리킨 메트릭·로그만 원시 시계열로 조회, LLM이 이상 여부 판단
```
이 순서는 FastMCP `instructions`에 박혀 있어 클라이언트 LLM이 따르게 된다.

## 설계 결정

- **임계값은 check_health에만 있다.** 임계값은 "어디부터 볼지" 고르는 용도(ok/warn/anomaly, 점수 없음)로만
  쓴다. `query_promql`은 원시 시계열만 돌려주고, 스파이크·추세 판단은 LLM이 한다.
  KG 노드의 `gate`는 판단 기준이 아니라 참고값이다.
- **KG는 Neo4j에 있다.** `catalog/kg/ontology.yaml`이 단일 소스이고, `make seed`로 적재한다.
  서버는 Neo4j만 읽는다. 엣지 방향은 증상 → 원인이다.
- **4개 체인이 `app_query_latency` 노드를 공유한다.** 지연의 원인을 backend의 wait 유형으로
  감별한다: Lock이면 앱 lock 경합, CPU면 컨테이너 throttling, IO면 스토리지.
- **클러스터는 만들지 않는다.** 현재 kubeconfig context의 클러스터에 `helm install`만 한다.
- **옵저버빌리티 스택은 서브차트 없이 평이한 매니페스트로 둔다.** 전부 단일 replica다.
- **postgres_exporter는 사이드카다.** 그래서 앱 메트릭에 `pod=postgres-0` 라벨이 붙어 다른 계층과 같은 키로 조회된다.
- **kubelet/cAdvisor는 API 서버 프록시로 scrape한다.** 매니지드 클러스터에서도 동작한다.
- **MCP tool은 전부 read-only다.**

## 클러스터를 받으면 설치 전에 확인할 것

아래 항목 중 하나라도 맞지 않으면 `helm install`이 실패하거나 파드가 뜨지 않는다.

| # | 확인 | 명령 | 안 맞으면 생기는 일 → 대응 |
|---|---|---|---|
| 1 | 노드 CPU 아키텍처 | `kubectl get nodes -L kubernetes.io/arch` | 맥(arm64)에서 빌드한 MCP 이미지를 amd64 노드에서 실행하면 `CrashLoopBackOff`(exec format error)가 난다 → `docker buildx build --platform linux/amd64 -t $IMAGE --push .`로 빌드한다 |
| 2 | 이미지 레지스트리 | 클러스터가 pull할 수 있는 레지스트리가 있는가 | mcp 파드가 `ImagePullBackOff` → 레지스트리에 push하고 `IMAGE=<registry>/...`로 배포한다. private 레지스트리면 pull secret이 필요한데, 현재 차트에는 그 설정이 없다 |
| 3 | default StorageClass | `kubectl get sc` (`(default)` 표시) | postgres PVC가 `Pending`, 파드도 `Pending` → `--set postgres.storageClass=<이름>` |
| 4 | 스토리지 종류 | StorageClass의 provisioner | local-path류(노드 디스크의 디렉터리)면 `fault-disk`가 안전장치로 실행을 거부하고, `pvc_*` 메트릭도 비어 있다. 디스크 시나리오에는 크기가 정해진 실제 볼륨(CSI)이 필요하다 |
| 5 | 권한 | `kubectl auth can-i create clusterrole` | `yes`가 아니면 설치가 실패한다(Prometheus, kube-state-metrics가 ClusterRole을 쓴다) → 관리자 권한을 요청한다 |
| 6 | Pod Security | `kubectl get ns --show-labels`, 이 namespace에 `pod-security.kubernetes.io/enforce` 라벨이 붙는지 / OpenShift인지 | restricted·baseline 강제 시 node-exporter(hostNetwork, hostPID, hostPath)와 promtail(hostPath)이 거부된다 → namespace를 privileged로 두거나 관리자와 협의한다 |
| 7 | 기존 모니터링 | `kubectl get ds,deploy -A \| grep -E "node-exporter\|kube-state-metrics"` | 기존 node-exporter와 9100 포트가 충돌한다 → `--set nodeExporter.enabled=false` (kube-state-metrics도 `kubeStateMetrics.enabled=false`) |
| 8 | 외부 이미지 pull | 노드가 Docker Hub / quay.io / registry.k8s.io에 접근 가능한가 | 폐쇄망이나 rate limit이면 서드파티 이미지가 `ImagePullBackOff` → 사내 미러로 `values.yaml`의 이미지 경로를 바꾼다 |
| 9 | 컨테이너 로그 경로 | containerd / cri-o 런타임인가(`kubectl get nodes -o wide`의 CONTAINER-RUNTIME) | 로그가 `/var/log/pods`에 없으면 Loki가 비어 있다 |
| 10 | 리소스 | namespace에 ResourceQuota/LimitRange가 있는가: `kubectl get quota,limitrange -n semantic-obs` | 요청 합계(메모리 약 1.3Gi)가 쿼터를 넘으면 파드 생성이 거부된다 |

설치 후 확인:
```bash
make status                                   # 모든 파드 Running/Ready
kubectl -n semantic-obs get pvc               # data-postgres-0 Bound
make pf   # 다른 터미널에서:
curl -s localhost:9090/api/v1/targets | grep -o '"health":"[a-z]*"' | sort | uniq -c   # 전부 up (5개 job)
curl -s localhost:3100/loki/api/v1/label/pod/values                                    # postgres-0 포함
```
참고: Neo4j는 emptyDir라서 파드가 재시작되면 KG가 사라진다 → `make seed`를 다시 한다.

## 사용법

```bash
make image IMAGE=<registry>/semantic-obs-mcp:0.1.0   # 빌드 + push
make up    IMAGE=<registry>/semantic-obs-mcp:0.1.0   # helm install + KG 적재 + pgbench 테이블 생성
make pf                                              # (별도 터미널) prometheus 9090, loki 3100, neo4j 7687/7474, mcp 8000
```
MCP 클라이언트 연결:
- HTTP(클러스터 안 서버): `http://localhost:8000/mcp`
- stdio(로컬 서버, `make pf` 필요): `cp .env.example .env` 후
  `claude mcp add semantic-obs -- uv --directory <repo> run python src/server.py`

그 외 타깃:
- `make mcp-dev [TRANSPORT=http]`: 로컬 서버 실행
- `make status`: 파드 상태 확인
- `make down`: 릴리스와 PVC 삭제

## 장애 주입 (`eval/scenarios.md` 참고)

| 명령 | 하는 일 | 기대 근본 원인 |
|---|---|---|
| `make fault-oom` | memory limit 256Mi로 축소 + `work_mem` 큰 정렬 | container: 메모리 limit |
| `make fault-cpu` | CPU limit 100m + CPU 쿼리 8개 동시 실행 | container: CPU throttling |
| `make fault-disk [MODE=inodes]` | PVC를 컨테이너 안에서 가득 채움 + 쓰기 부하 | node/storage: 공간 또는 inode 부족 |
| `make fault-lock` | 긴 트랜잭션 1개 + 핫 row 경합 클라이언트 10개 | application: lock 경합 |
| `make fault-clear` | 부하 파드 삭제, 채운 파일 삭제, 차트 기본값 복원 | |

다음 시나리오 전에 5분 이상 기다린다. 기본 window가 5m이라 이전 장애 신호가 남는다.

## 파일 설명

### 루트
| 파일 | 용도 |
|---|---|
| `Makefile` | `image`, `deploy`, `seed`, `up`, `pf`, `mcp-dev`, `fault-*`, `status`, `down` |
| `pyproject.toml`, `uv.lock` | Python 의존성(fastmcp, neo4j, httpx, pyyaml, python-dotenv). lock으로 이미지 빌드를 재현 |
| `Dockerfile` | python:3.13-slim + uv, 비루트 유저, `/health` HEALTHCHECK. `python src/server.py`로 직접 실행 |
| `.env.example` | 로컬 실행용 백엔드 주소와 대상 namespace/pod/mountpoint |

### `src/` — MCP 서버
| 파일 | 용도 |
|---|---|
| `server.py` | FastMCP 인스턴스, `instructions`(STEP 순서), tool 9개, `/health`. `get_diagnosis`의 Cypher도 여기 있다 |
| `health.py` | `check_health` 구현. probe를 병렬 실행하고 임계값으로 ok/warn/anomaly 판정, 이상 probe 정렬 |
| `catalog.py` | catalog YAML 로드, 플레이스홀더(`{namespace}{pod}{container}{window}{mountpoint}`) 치환 |
| `prom_client.py` | Prometheus instant / range 쿼리 |
| `loki_client.py` | Loki 로그 조회와 라인 수 집계 |
| `neo4j_client.py` | Neo4j 드라이버와 읽기 쿼리 |
| `config.py` | 환경변수 로딩 |

### `catalog/` — 쿼리와 지식 (코드와 분리)
| 파일 | 용도 |
|---|---|
| `metrics/node.yaml` | node-exporter: 파일시스템 여유 공간·inode, 노드 CPU·메모리 |
| `metrics/kubernetes.yaml` | kube-state-metrics: 재시작, OOMKilled, NotReady, DiskPressure. kubelet: PVC 여유 공간·inode |
| `metrics/container.yaml` | cAdvisor: 메모리/limit 비율, CFS throttle 비율, CPU 사용량·limit |
| `metrics/application.yaml` | postgres_exporter: up, active·blocked backend, wait 유형별 backend, 최장 쿼리·트랜잭션, deadlock, lock, TPS |
| `logs/application.yaml` | LogQL: crash, 연결 끊김, No space, checkpoint, deadlock, lock wait, slow query, ERROR |
| `health_probes.yaml` | check_health가 돌리는 probe 목록: 참조하는 metric/log, 임계값, 진입할 KG 노드 |
| `kg/ontology.yaml` | KG 단일 소스. 노드(gate, 확인할 metric/log, note, action, terminal)와 branches(증상→원인) |

### `scripts/`
| 파일 | 용도 |
|---|---|
| `seed_kg.py` | ontology 검증(id 존재 여부) 후 Neo4j를 비우고 MERGE로 적재. `--check`는 검증만 |
| `faults/_common.sh` | 공통 함수: psql/exec, pgbench 초기화, helm 값 패치, 부하 파드 생성 |
| `faults/oom.sh`, `cpu_throttle.sh`, `disk_pressure.sh`, `lock_contention.sh` | 장애 4종 주입 |
| `faults/clear.sh` | 장애 원복 |

### `helm/semantic-obs/`
| 파일 | 용도 |
|---|---|
| `Chart.yaml`, `values.yaml` | 차트 정의. 이미지, 접속정보, 비밀번호, retention, 리소스 limit, PVC 크기 |
| `templates/postgres.yaml` | postgres StatefulSet(PVC) + exporter 사이드카, Service, ConfigMap(로그 설정, exporter 커스텀 쿼리) |
| `templates/neo4j.yaml` | Neo4j Community 단일 파드. KG는 `make seed`로 다시 적재하므로 emptyDir를 쓴다 |
| `templates/mcp.yaml` | MCP 서버 Deployment + Service |
| `templates/observability-prometheus.yaml` | Prometheus + RBAC. 파드 annotation 대상, kubelet, cAdvisor를 scrape |
| `templates/observability-loki.yaml` | Loki single-binary, filesystem 스토리지 |
| `templates/observability-promtail.yaml` | promtail DaemonSet. `/var/log/pods/<ns>_*`를 tail하고 경로에서 라벨을 뽑는다 |
| `templates/observability-exporters.yaml` | node-exporter, kube-state-metrics (on/off 가능) |

### `eval/`
| 파일 | 용도 |
|---|---|
| `scenarios.md` | 장애별 주입 명령, 기대 근본 원인 계층·KG 경로·근거 지표, 수동 확인 절차 |
