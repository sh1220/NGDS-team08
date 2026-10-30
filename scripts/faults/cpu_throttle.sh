#!/usr/bin/env bash
# Fault 2 — CPU throttling: cap postgres CPU at 100m and run concurrent CPU-heavy queries.
source "$(dirname "$0")/_common.sh"
ensure_pgbench
helm_patch --set postgres.resources.limits.cpu=100m
load_pod pgload-cpu '
cat > /tmp/cpu.sql <<SQL
SELECT count(*) FROM generate_series(1, 300000) g WHERE md5(g::text) LIKE '\''a%'\'';
SQL
pgbench -n -c 8 -j 2 -T 1800 -f /tmp/cpu.sql -P 30'
echo "Expect: throttle ratio > 0.25, active backends on CPU, long queries within ~2 min. Root cause: container CPU limit."
