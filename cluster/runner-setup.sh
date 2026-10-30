#!/bin/bash
# 앱 러너 LXC 112(192.168.45.239)를 이 레포의 self-hosted runner(라벨 ngds)로 만든다. 관리자가 맥에서 실행, 재실행 가능.
#   전제: 홈랩 tunnels.sh(SOCKS 11080), 관리자 kubeconfig(KUBECONFIG), gh 로그인
# 러너가 받는 권한: ngds 네임스페이스의 ngds-ci Role(배포 리소스만, exec 없음) 하나뿐 (Proxmox·노드·클러스터 관리자 권한 없음)
# 수집기(privileged) 배포 권한은 러너 디스크가 아니라 Environment secret으로만 준다 (monitoring.yml)
# 한계: runner group/Environment(유료)로 워크플로를 제한하지 않았다 → 레포를 private, 협업자만으로 유지한다
set -euo pipefail
REPO=sh1220/NGDS-team08 HOST=192.168.45.239 KEY=~/.ssh/id_ed25519_homelab
HELM=4.3.1 KUBECTL=1.37.1
RUNNER=$(gh api repos/actions/runner/releases/latest --jq .tag_name | tr -d v)
RUNNER_SHA=$(gh api repos/actions/runner/releases/latest --jq ".assets[] | select(.name==\"actions-runner-linux-x64-$RUNNER.tar.gz\") | .digest" | cut -d: -f2)
r() { ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ProxyCommand='nc -X 5 -x 127.0.0.1:11080 %h %p' -i $KEY root@$HOST "$@"; }

echo "== 도구 (sha256 검증)"
r "HELM=$HELM KUBECTL=$KUBECTL sh -eu" <<'X'
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update && apt-get -qq install -y curl ca-certificates git >/dev/null
cd "$(mktemp -d)"
check() { echo "$1  $2" | sha256sum -c - >/dev/null || { echo "체크섬 불일치: $2" >&2; exit 1; }; }
curl -fsSLo helm.tgz https://get.helm.sh/helm-v$HELM-linux-amd64.tar.gz
check "$(curl -fsSL https://get.helm.sh/helm-v$HELM-linux-amd64.tar.gz.sha256sum | awk '{print $1}')" helm.tgz
tar xzf helm.tgz --strip-components=1 -C /usr/local/bin linux-amd64/helm
curl -fsSLo kubectl https://dl.k8s.io/release/v$KUBECTL/bin/linux/amd64/kubectl
check "$(curl -fsSL https://dl.k8s.io/release/v$KUBECTL/bin/linux/amd64/kubectl.sha256)" kubectl
install -m 755 kubectl /usr/local/bin/kubectl
id runner >/dev/null 2>&1 || useradd -m -s /bin/bash runner
install -d -o runner -g runner -m 700 ~runner/.kube
X

echo "== 네임스페이스 전용 kubeconfig"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
(cd "$T" && GROUP=ngds-ci "$OLDPWD/cluster/issue-kubeconfig.sh" ci-runner https://192.168.45.241:6443 >/dev/null)
r "cat > ~runner/.kube/config && chown runner:runner ~runner/.kube/config && chmod 600 ~runner/.kube/config" < "$T/kubeconfig-ci-runner.yaml"

echo "== 수집기 배포용 kubeconfig → GitHub Environment secret (러너 디스크에 두지 않는다)"
# Environment "monitoring": main 브랜치만 + 관리자 승인. 없으면 만든다
ME=$(gh api user --jq .id)
gh api -X PUT repos/$REPO/environments/monitoring --input - >/dev/null <<J
{"reviewers":[{"type":"User","id":$ME}],"prevent_self_review":false,"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
J
gh api repos/$REPO/environments/monitoring/deployment-branch-policies --jq '.branch_policies[].name' | grep -qx main ||
  gh api -X POST repos/$REPO/environments/monitoring/deployment-branch-policies -f name=main -f type=branch >/dev/null
(cd "$T" && GROUP=ngds-monitoring-ci "$OLDPWD/cluster/issue-kubeconfig.sh" ci-monitoring https://192.168.45.241:6443 >/dev/null)
# issue-kubeconfig.sh는 기본 네임스페이스를 ngds로 넣는다 → 차트 명령은 -n으로 지정하므로 그대로 둔다
gh secret set MONITORING_KUBECONFIG --env monitoring -R $REPO < "$T/kubeconfig-ci-monitoring.yaml"

echo "== runner $RUNNER 등록"
REGISTERED=$(gh api repos/$REPO/actions/runners --jq '[.runners[].name] | index("app-runner") != null' | sed 's/true/yes/;s/false/no/')
TOKEN=$(gh api -X POST repos/$REPO/actions/runners/registration-token --jq .token)
r "RUNNER=$RUNNER SHA=$RUNNER_SHA REPO=$REPO REGISTERED=$REGISTERED sh -eu" <<X
D=~runner/actions-runner; mkdir -p \$D && cd \$D
if [ ! -x ./config.sh ] || [ "\$(cat .version 2>/dev/null)" != "\$RUNNER" ]; then
  curl -fsSLo runner.tgz https://github.com/actions/runner/releases/download/v\$RUNNER/actions-runner-linux-x64-\$RUNNER.tar.gz
  echo "\$SHA  runner.tgz" | sha256sum -c - >/dev/null
  tar xzf runner.tgz && rm runner.tgz && echo \$RUNNER > .version
  ./bin/installdependencies.sh >/dev/null 2>&1
fi
chown -R runner:runner \$D
[ "\$REGISTERED" = yes ] || rm -f .runner .credentials .credentials_rsaparams
[ -f .runner ] || runuser -u runner -- ./config.sh --unattended --replace --url https://github.com/\$REPO --token $TOKEN --name app-runner --labels ngds >/dev/null
[ -f .service ] || ./svc.sh install runner >/dev/null
./svc.sh stop >/dev/null 2>&1 || true; ./svc.sh start >/dev/null
X
# 이미 등록된 러너는 config.sh를 건너뛰므로 사용자 라벨을 API로 맞춘다 (기본 라벨 self-hosted 등은 유지됨)
ID=$(gh api repos/$REPO/actions/runners --jq '.runners[] | select(.name=="app-runner") | .id')
gh api -X PUT repos/$REPO/actions/runners/$ID/labels -f 'labels[]=ngds' >/dev/null
gh api repos/$REPO/actions/runners --jq '.runners[] | "\(.name) \(.status) \(.labels | map(.name) | join(","))"'
