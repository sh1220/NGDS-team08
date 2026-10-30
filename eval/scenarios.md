# Fault scenarios — manual evaluation script

Common procedure (each scenario):
1. `make fault-clear`, then **wait at least 5 minutes** (keeps the previous fault's signal out of the default 5m window).
2. Run the injection command and wait 1–2 minutes.
3. Ask the MCP client: "Is this app healthy right now? If not, find the root cause."
4. Check: the agent goes **check_health → get_diagnosis(enters_node …) → query_promql/query_logql** in order,
   and the final answer names the expected root-cause layer, KG node, and evidence below.
5. `make fault-clear`

| # | Inject | Expected root-cause layer / KG node | Expected causal path (KG) | Evidence metric/log |
|---|------|---------------------------|------------------|----------------|
| 1 | `make fault-oom` | **container** / `ctr_mem_near_limit` | app_conn_errors → k8s_pod_restart → k8s_oomkilled → ctr_mem_near_limit | `pod_last_terminated_oom`=1, `pod_restarts`>0, `ctr_mem_limit_bytes`(256Mi), log `pg_server_crash`, `pg_client_conn_lost` ("server closed the connection") |
| 2 | `make fault-cpu` | **container** / `ctr_cpu_throttling` | app_backends_piling → app_query_latency → ctr_cpu_throttling | `ctr_cpu_throttle_ratio`≈1.0, `ctr_cpu_usage_cores`≈`ctr_cpu_limit_cores`(0.1), `pg_backends_by_wait{CPU}` high, `pg_blocked_backends`=0, `node_cpu_busy_ratio` low |
| 3 | `make fault-disk` (or `MODE=inodes`) | **node** / `node_fs_bytes_low` (`node_fs_inodes_low`) | app_write_errors → node_fs_bytes_low / node_fs_inodes_low | `node_fs_avail_ratio`<0.05 (or `node_fs_inodes_free_ratio`<0.05), log `pg_no_space` ("No space left on device") |
| 4 | `make fault-lock` | **application** / `app_long_tx_holder` (+`app_deadlocks`) | app_backends_piling → app_query_latency → app_lock_contention → app_long_tx_holder | `pg_blocked_backends`≈10, `pg_backends_by_wait{Lock}` high, `pg_max_tx_duration` rising, `ctr_cpu_throttle_ratio`=0, log `pg_lock_wait` |

Pass criterion: the correct root-cause layer + evidence metric in at least 3 of the 4 scenarios.

Notes
- In scenario 2, `k8s_not_ready` can also fire (the readiness probe times out under CPU starvation). The KG branch
  `k8s_pod_restart → ctr_cpu_throttling` covers this case.
- In scenario 1 the memory spike can be shorter than the scrape interval (15s), so the peak ratio may not breach the gate.
  The OOMKilled reason (kubernetes) + the lowered limit is sufficient evidence (stated in the node's note).
- `fault-disk` fills the postgres PVC from inside the container. If the volume shows more than 5GB free (storage that is really the node disk, such as local-path), it refuses to run (`FORCE=1` overrides).

Out of scope (follow-up work): quantitative scoring with LLM-as-judge, automated repeated runs.
