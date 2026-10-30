#!/usr/bin/env bash
# Fault 3 — disk/inode pressure on the postgres data volume (PVC), filled from inside the container.
#   ./disk_pressure.sh [bytes|inodes]   (default: bytes)
# Safety: if the volume shows more than MAX_FILL_GB free (e.g. local-path storage that is really
# the node's root disk) it refuses unless FORCE=1, to avoid filling a shared node disk.
source "$(dirname "$0")/_common.sh"
MODE="${1:-bytes}"
MAX_FILL_GB="${MAX_FILL_GB:-5}"
DATA=/var/lib/postgresql/data
ensure_pgbench
avail_kb=$(pg_exec "df -k --output=avail $DATA | tail -1" | tr -d ' ')
if [ "$avail_kb" -gt $((MAX_FILL_GB * 1024 * 1024)) ] && [ "${FORCE:-0}" != 1 ]; then
  echo "refusing: data volume has $((avail_kb / 1024 / 1024))GB free (> ${MAX_FILL_GB}GB) — probably the node's disk."
  echo "Use a storage class with a real sized volume, or rerun with FORCE=1."; exit 1
fi
case "$MODE" in
  # leave ~4MB so the next WAL segment (16MB) / relation extension fails
  bytes)  pg_exec "dd if=/dev/zero of=$DATA/_fault_fill bs=1M count=$(( avail_kb / 1024 - 4 )) status=none; df -h $DATA" ;;
  inodes) pg_exec "mkdir -p $DATA/_fault_inodes && cd $DATA/_fault_inodes && (seq 1 2000000 | xargs touch 2>/dev/null || true); df -i $DATA" ;;
  *) echo "usage: $0 [bytes|inodes]"; exit 1 ;;
esac
load_pod pgload-disk '
until pgbench -n -c 4 -j 2 -T 1800 -P 30; do sleep 5; until pg_isready -q; do sleep 2; done; done'
echo "Expect: write failures (No space left on device), possibly PANIC/restart. Root cause: storage ($MODE)."
