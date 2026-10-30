# NGDS-team08 — Semantic Observability RCA

차세대 분산 시스템(NGDS, 차분시) 8팀 프로젝트.
Kubernetes 위의 PostgreSQL 하나를 대상으로 삼아, node → kubernetes → container → application 계층의 메트릭과 로그를 본다.
MCP 서버는 **Neo4j에 저장된 인과 지식 그래프(KG)를 Cypher로 탐색**하고, LLM은 이를 따라 장애의 근본 원인을 찾는다.
MAPE-K 관점에서 Knowledge는 그래프로 외부화하고, Analyze는 LLM과 MCP가 맡는다.

## 홈랩 배포 구조

| 네임스페이스 | Pod Security | 내용 | 배포 주체 | 팀원 권한 |
|---|---|---|---|---|
| `ngds` | restricted | postgres(+exporter 사이드카), neo4j, mcp — `charts/ngds` | main 머지 → `deploy.yml` → 앱 러너(LXC 112, 라벨 `ngds`) | 배포·exec·port-forward·부하 파드 생성 |
| `ngds-monitoring` | privileged | Prometheus, Loki, promtail, node-exporter, kube-state-metrics — `charts/ngds-monitoring` | 홈랩 인프라 레포 helmfile(관리자), 이 레포 커밋 SHA로 고정 | 조회·로그, Prometheus·Loki Service 프록시만 (port-forward 없음) |

- **두 네임스페이스로 나눈 이유:** 수집기는 hostPath, hostNetwork, ClusterRole이 필요하다. 그 네임스페이스에 파드를 만들 수 있으면 노드 root를 잡을 수 있다. 그래서 팀원과 앱 러너는 restricted인 `ngds`에서만 파드를 만든다.
- **`charts/ngds-monitoring`을 바꾸려면:** 이 레포에서 PR을 머지한 뒤, 관리자가 인프라 레포의 고정 SHA를 올려야 반영된다.
- **MCP의 수집기 주소:** `prometheus.ngds-monitoring:9090`, `loki.ngds-monitoring:3100`.
- **Prometheus가 kubelet/cAdvisor를 긁는 방법:** API 서버 프록시(`nodes/proxy`, kubelet exec까지 열리는 권한)는 쓰지 않는다. 노드 `:10250`에 직접 붙고 `nodes/metrics` 권한만 쓴다.
- **kube-state-metrics 권한:** 수집하는 리소스만 읽는다(Secret 제외).
- **PVC:** 기본 StorageClass(`proxmox-zfs`, Proxmox CSI)로 만들어진다. 크기가 정해진 실제 디스크라 디스크 장애 시나리오를 그대로 돌릴 수 있다.
- **이미지:** `ghcr.io/sh1220/ngds-team08-mcp`(public). 이미지에 코드가 들어가므로 비밀값을 넣지 않는다.

### CI/CD
| 워크플로 | 트리거 | 러너 | 내용 |
|---|---|---|---|
| `ci.yml` | PR → main | GitHub 호스팅 | py_compile, `bash -n`, 두 차트 lint/template, docker build |
| `deploy.yml` | main push(`src/`, `catalog/`, `charts/ngds/`, `Dockerfile`, 의존성), 수동 | 호스팅(빌드·GHCR push) → 앱 러너(배포) | `helm upgrade --install ngds charts/ngds`, 태그 = 커밋 7자리 |

배포는 `helm upgrade`로 차트 기본값을 다시 적용한다. 그래서 장애 주입으로 바꾼 limit 같은 값은 배포할 때마다 원복된다.

### 팀원 시작하기
1. 관리자에게 `kubeconfig-<이름>.yaml`을 받아 `export KUBECONFIG=...`로 지정한다. `ngds` 네임스페이스 전용이고 90일 동안 유효하다.
2. 새 클러스터가 올라오면 한 번 `make seed`를 실행한다. KG를 적재하고 pgbench 테이블을 만든다. Neo4j는 emptyDir라서 neo4j 파드가 재시작될 때마다 다시 해야 한다.
3. 다른 터미널에서 `make pf`를 실행한다. neo4j 7687/7474, mcp 8000 포트 포워딩과 Prometheus·Loki용 `kubectl proxy :8001`이 열린다. 주소는 `.env.example` 참고.
4. 장애 주입: `make fault-*`, 원복: `make fault-clear`. 아래 표 참고.

### 관리자
```bash
make cluster-init                                  # 네임스페이스 2개·권한 (재적용 가능)
cluster/issue-kubeconfig.sh <팀원이름> [API 주소]   # 팀원 kubeconfig (그룹 ngds-devs, 90일)
cluster/runner-setup.sh                            # 앱 러너 등록 (그룹 ngds-ci, 90일마다 재실행해 kubeconfig 갱신)
```
- 프로젝트를 끝낼 때: 인프라 레포에서 `ngds-monitoring` 릴리스를 제거한 뒤 `kubectl delete ns ngds ngds-monitoring`.
- **경계 규칙:** 앱 러너와 팀원은 `ngds` 안의 것만 설치한다. 클러스터 전역 리소스(ClusterRole, CRD 등)나 privileged 워크로드는 인프라 레포의 helmfile을 거친다(권한상으로도 막혀 있다).

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
- **kubelet/cAdvisor는 노드 :10250에 직접 붙어 scrape한다.** `nodes/metrics` 권한만 쓴다. API 서버 프록시(`nodes/proxy`)는 kubelet exec까지 열려서 쓰지 않는다.
- **MCP tool은 전부 read-only다.**

## 다른 클러스터에 설치할 때
홈랩에서는 이미 맞춰져 있다(amd64, GHCR public, 기본 StorageClass가 CSI, 네임스페이스와 권한은 `make cluster-init`).
다른 클러스터에서는 다음을 확인한다.
- 노드 아키텍처
- 기본 StorageClass
- ClusterRole 생성 권한(수집기 차트)
- Pod Security: `ngds-monitoring`은 privileged여야 한다
- 기존 node-exporter와의 9100 포트 충돌. 충돌하면 `nodeExporter.enabled=false`

## 사용법

```bash
make image    # (직접 테스트할 때) amd64 빌드 + GHCR push. 평소에는 main 머지 시 CI가 한다
make up       # helm upgrade --install ngds + KG 적재 + pgbench 테이블 생성
make pf       # (별도 터미널) neo4j 7687/7474, mcp 8000, kubectl proxy 8001(Prometheus·Loki)
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

### `charts/ngds/` (앱, `ngds`)
| 파일 | 용도 |
|---|---|
| `Chart.yaml`, `values.yaml` | 차트 정의. 이미지, 접속정보, 비밀번호, retention, 리소스 limit, PVC 크기 |
| `templates/postgres.yaml` | postgres StatefulSet(PVC, uid 999로 실행) + exporter 사이드카, Service, ConfigMap(로그 설정, exporter 커스텀 쿼리) |
| `templates/neo4j.yaml` | Neo4j Community 단일 파드. KG는 `make seed`로 다시 적재하므로 emptyDir를 쓴다 |
| `templates/mcp.yaml` | MCP 서버 Deployment + Service |

### `charts/ngds-monitoring/` (수집기, `ngds-monitoring`)
| 파일 | 용도 |
|---|---|
| `values.yaml` | `targetNamespace`(수집 대상 앱 네임스페이스), 이미지, retention |
| `templates/prometheus.yaml` | Prometheus + ClusterRole(조회 전용). 두 네임스페이스의 annotation 파드, kubelet, cAdvisor(노드 :10250 직접)를 scrape |
| `templates/loki.yaml` | Loki single-binary, filesystem 스토리지 |
| `templates/promtail.yaml` | promtail DaemonSet. `/var/log/pods/ngds_*`를 tail하고 경로에서 라벨을 뽑는다 |
| `templates/exporters.yaml` | node-exporter, kube-state-metrics (on/off 가능) |

### `cluster/` (관리자)
| 파일 | 용도 |
|---|---|
| `namespace-rbac.yaml` | 네임스페이스 2개(PSA 라벨), 팀원(`ngds-devs`)·앱 러너(`ngds-ci`) Role |
| `issue-kubeconfig.sh` | CSR API로 90일 kubeconfig 발급 |
| `runner-setup.sh` | 앱 러너 LXC 112 등록·kubeconfig 갱신 |

### `eval/`
| 파일 | 용도 |
|---|---|
| `scenarios.md` | 장애별 주입 명령, 기대 근본 원인 계층·KG 경로·근거 지표, 수동 확인 절차 |
