#!/usr/bin/env bash
# Fault 1 — OOMKilled: shrink the postgres memory limit, then run memory-hungry sorts
# (work_mem large) so the cgroup OOM killer kills the container -> restart -> clients disconnected.
source "$(dirname "$0")/_common.sh"
ensure_pgbench
helm_patch --set postgres.resources.limits.memory=256Mi
load_pod pgload-oom '
for i in 1 2 3; do
  echo "== memory-heavy sort round $i"
  psql -c "SET work_mem = '\''1GB'\''; SELECT count(*) FROM (SELECT g, md5(g::text) m FROM generate_series(1, 6000000) g ORDER BY m) s;" || true
  sleep 40
  until pg_isready -q; do sleep 2; done
done
echo done; sleep 3600'
echo "Expect: OOMKilled + restarts within ~1 min. Root cause: container memory limit."
