#!/bin/bash
# 팀원용 kubeconfig 발급 (관리자가 실행). 쿠버네티스 CSR API로 그룹 ngds-devs 인증서를 90일짜리로 서명받는다.
# 사용: [GROUP=ngds-ci] cluster/issue-kubeconfig.sh <이름> [API 서버 주소] (기본 그룹 ngds-devs = 팀원)  →  kubeconfig-<이름>.yaml (팀원에게 전달, 커밋 금지)
# 회수: kubectl delete rolebinding -n ngds ngds-devs 하면 그룹 전체가, 인증서 만료(90일)로 개인이 끊긴다.
set -euo pipefail
NAME=${1:?이름}; GROUP=${GROUP:-ngds-devs}; SERVER=${2:-$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout "$T/key.pem" -subj "/CN=$NAME/O=$GROUP" -out "$T/csr.pem" 2>/dev/null
kubectl delete csr "ngds-$NAME" --ignore-not-found >/dev/null
cat <<YAML | kubectl apply -f - >/dev/null
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata: { name: ngds-$NAME }
spec:
  request: $(base64 < "$T/csr.pem" | tr -d '\n')
  signerName: kubernetes.io/kube-apiserver-client
  expirationSeconds: 7776000
  usages: [client auth]
YAML
kubectl certificate approve "ngds-$NAME" >/dev/null
for _ in $(seq 20); do C=$(kubectl get csr "ngds-$NAME" -o jsonpath='{.status.certificate}'); [ -n "$C" ] && break; sleep 1; done
[ -n "$C" ] || { echo "서명 실패" >&2; exit 1; }
CA=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
OUT="kubeconfig-$NAME.yaml"; umask 077
cat > "$OUT" <<YAML
apiVersion: v1
kind: Config
clusters: [{ name: homelab, cluster: { server: "$SERVER", certificate-authority-data: $CA } }]
users: [{ name: $NAME, user: { client-certificate-data: $C, client-key-data: $(base64 < "$T/key.pem" | tr -d '\n') } }]
contexts: [{ name: ngds, context: { cluster: homelab, user: $NAME, namespace: ngds } }]
current-context: ngds
YAML
kubectl delete csr "ngds-$NAME" >/dev/null
echo "$OUT (90일, 네임스페이스 ngds 전용)"
