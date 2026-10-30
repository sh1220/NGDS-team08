#!/usr/bin/env bash
# Fault 4 — app lock contention: one long transaction holds a hot row, and pgbench clients
# update a few hot rows in random order inside slow transactions (lock waits + deadlocks).
source "$(dirname "$0")/_common.sh"
ensure_pgbench
load_pod pgload-lock-holder '
psql -c "BEGIN; UPDATE pgbench_accounts SET abalance = abalance WHERE aid = 1; SELECT pg_sleep(1800); COMMIT;"'
load_pod pgload-lock '
cat > /tmp/lock.sql <<SQL
\set a random(1, 4)
\set b random(1, 4)
BEGIN;
UPDATE pgbench_accounts SET abalance = abalance + 1 WHERE aid = :a;
SELECT pg_sleep(0.5);
UPDATE pgbench_accounts SET abalance = abalance - 1 WHERE aid = :b;
END;
SQL
pgbench -n -c 10 -j 2 -T 1800 -f /tmp/lock.sql --max-tries=100 -P 30'
echo "Expect: blocked backends, lock-wait + deadlock logs within ~1 min. Root cause: application lock contention."
