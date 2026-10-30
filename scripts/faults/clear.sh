#!/usr/bin/env bash
# Revert all faults: stop load pods, remove fill files, restore chart default values (keeps mcp.image).
source "$(dirname "$0")/_common.sh"
kubectl -n "$NS" delete pod -l fault=load --ignore-not-found --wait=true
pg_exec "rm -rf /var/lib/postgresql/data/_fault_fill /var/lib/postgresql/data/_fault_inodes" || true
IMAGE=$(helm get values "$RELEASE" -n "$NS" -o json | python3 -c "import json,sys; print(json.load(sys.stdin).get('mcp',{}).get('image',''))")
helm upgrade "$RELEASE" "$CHART" -n "$NS" --reset-values ${IMAGE:+--set mcp.image=$IMAGE} >/dev/null
kubectl -n "$NS" rollout status sts/postgres --timeout=180s
kubectl -n "$NS" wait --for=condition=Ready pod/postgres-0 --timeout=180s >/dev/null
psql_exec "select pg_terminate_backend(pid) from pg_stat_activity where backend_type='client backend' and pid <> pg_backend_pid()" >/dev/null || true
echo "cleared"
