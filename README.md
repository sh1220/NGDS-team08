# chabunsi

차세대 분산 시스템(NGDS, 차분시) 8팀 프로젝트. FastMCP 서버를 홈랩 쿠버네티스에 헬름으로 배포한다.

| 경로 | 내용 |
|---|---|
| `app/` | FastMCP 서버 (`/mcp`, 메트릭 `:9000/metrics`) |
| `Dockerfile` | 이미지 (`ghcr.io/sh1220/ngds-team08-mcp`, **public** 패키지 — 코드가 이미지에 들어가니 비밀값을 넣지 말 것) |
| `charts/chabunsi/` | 헬름 차트 (Deployment, Service, ServiceMonitor) |
| `cluster/` | 네임스페이스·팀원 권한, 팀원 kubeconfig 발급 스크립트 (관리자용) |
| `Makefile` | build / push / deploy / undeploy |

이미지 이름 규칙: `ghcr.io/sh1220/ngds-team08-<구성요소>` (GHCR은 소문자만 허용)

## CI/CD
| 워크플로 | 트리거 | 러너 | 내용 |
|---|---|---|---|
| `ci.yml` | PR → main | GitHub 호스팅 | py_compile, helm lint/template, docker build |
| `deploy.yml` | main push(`app/`, `Dockerfile`, `charts/`), 수동 | 호스팅(빌드·GHCR push) → 홈랩 앱 러너(배포) | `helm upgrade --install --wait`, 태그 = 커밋 7자리 |

앱 러너(LXC 112, 라벨 `chabunsi`)는 이 네임스페이스 전용 kubeconfig만 가진다. 설정: `cluster/runner-setup.sh`(관리자, 재실행 가능).

## 수동 배포
```bash
make push          # 이미지 빌드 + GHCR 업로드 (docker login ghcr.io)
make deploy        # helm upgrade --install (네임스페이스 chabunsi)
make undeploy      # helm uninstall
```
팀원은 관리자에게 받은 `kubeconfig-<이름>.yaml`을 `KUBECONFIG`로 지정해서 쓴다. 이 kubeconfig는 `chabunsi` 네임스페이스 안에서만 동작한다.

## 클러스터와의 관계
- 클러스터(Proxmox, 노드, Cilium, 스토리지)는 별도 인프라 레포가 관리한다. 이 레포는 그 위에 앱만 올린다.
- PVC는 기본 StorageClass(`proxmox-zfs`)로 자동 생성된다. PV는 만들어진 노드에 묶인다.
- `Service type: LoadBalancer`는 Cilium이 집 LAN IP(.244~.254)를 준다. 외부 공개는 Cloudflare Tunnel 연결 후(예정).
- 메트릭: 클러스터에 Prometheus가 올라오면 `serviceMonitor.enabled=true`.

## 관리자 1회 설정
```bash
make cluster-init                                  # 네임스페이스·권한
cluster/issue-kubeconfig.sh <팀원이름> [API 주소]   # 팀원 kubeconfig (90일)
cluster/runner-setup.sh                            # 앱 러너 등록 (CI 배포용, 90일마다 재실행해 kubeconfig 갱신)
```
프로젝트 종료: `kubectl delete ns chabunsi`
