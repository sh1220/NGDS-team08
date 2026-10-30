#!/usr/bin/env bash
# Shared helpers for fault scripts. Can also be run directly: _common.sh <function>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NS="${NS:-ngds}"
RELEASE="${RELEASE:-ngds}"
CHART="${CHART:-$ROOT/charts/ngds}"
PG_IMAGE="postgres:16"
PGUSER=postgres PGPASSWORD=postgres PGDB=app

pg_exec() {  # run a shell command inside the postgres container
  kubectl -n "$NS" exec postgres-0 -c postgres -- sh -c "$1"
}

psql_exec() {  # run SQL inside the postgres pod
  kubectl -n "$NS" exec postgres-0 -c postgres -- psql -U "$PGUSER" -d "$PGDB" -tAc "$1"
}

ensure_pgbench() {
  kubectl -n "$NS" wait --for=condition=Ready pod/postgres-0 --timeout=180s >/dev/null
  if [ -z "$(psql_exec "select to_regclass('pgbench_accounts')")" ]; then
    echo "initializing pgbench tables (scale 5)"
    kubectl -n "$NS" exec postgres-0 -c postgres -- pgbench -U "$PGUSER" -i -s 5 -q "$PGDB"
  fi
}

# helm value patch on top of current values; postgres-0 is recreated
helm_patch() {
  helm upgrade "$RELEASE" "$CHART" -n "$NS" --reuse-values "$@" >/dev/null
  kubectl -n "$NS" rollout status sts/postgres --timeout=180s
  kubectl -n "$NS" wait --for=condition=Ready pod/postgres-0 --timeout=180s >/dev/null
}

# 네임스페이스가 Pod Security restricted라 부하 파드도 postgres 유저(uid 999)·권한 없이 띄운다
restricted_overrides() {
  printf '{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":999,"runAsGroup":999,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"%s","securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}' "$1"
}

# load_pod <name> <shell script>: client load in its own pod (removed by clear.sh)
load_pod() {
  kubectl -n "$NS" delete pod "$1" --ignore-not-found --wait=true >/dev/null
  kubectl -n "$NS" run "$1" --image="$PG_IMAGE" --restart=Never \
    --labels="fault=load" \
    --override-type=strategic --overrides="$(restricted_overrides "$1")" \
    --env="PGHOST=postgres" --env="PGUSER=$PGUSER" --env="PGPASSWORD=$PGPASSWORD" --env="PGDATABASE=$PGDB" \
    --command -- sh -c "until pg_isready -q; do sleep 2; done; $2"
  echo "load pod $1 started (logs: kubectl -n $NS logs -f $1)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ] && [ $# -gt 0 ]; then "$@"; fi
