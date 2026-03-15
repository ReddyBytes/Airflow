# 27 — Performance Optimization: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Key Config Parameters

| Parameter | Section | Default | Production Recommended | Effect |
|---|---|---|---|---|
| `min_file_process_interval` | `[scheduler]` | `30` | `300` | Re-parse each DAG file every N seconds. Higher = less DB/CPU load. |
| `parsing_processes` | `[scheduler]` | `2` | `4` | Parallel DAG file parsers. Set to CPU cores - 1. |
| `dag_file_processor_timeout` | `[scheduler]` | `50` | `120` | Kill file processor after N seconds. |
| `file_parsing_sort_mode` | `[scheduler]` | `modified_time` | `modified_time` | Parse recently-changed files first. |
| `scheduler_heartbeat_sec` | `[scheduler]` | `5` | `5` | Scheduler main loop frequency. |
| `max_active_runs_per_dag` | `[scheduler]` | `16` | `3–5` | Max concurrent runs per DAG. Prevents catchup runaway. |
| `max_active_tasks` | `[core]` | `16` | `100–200` | Global max running tasks. Scale with executor capacity. |
| `parallelism` | `[core]` | `32` | `128` | Max task instances running at once. |
| `worker_concurrency` | `[celery]` | `16` | `8–16` | Tasks per Celery worker. Lower for CPU-bound tasks. |
| `sql_alchemy_pool_size` | `[database]` | `5` | `5` | SQLAlchemy base connection pool. |
| `sql_alchemy_max_overflow` | `[database]` | `10` | `10` | Extra connections under peak load. |
| `sql_alchemy_pool_recycle` | `[database]` | `1800` | `1800` | Recycle idle DB connections. |
| `standalone_dag_processor` | `[scheduler]` | `False` | `True` | Run DAG processor as separate component (Airflow 3). |

---

## Sensor Mode Comparison

| Mode | Worker Slot | Concurrent Sensors | Setup | Recommended |
|---|---|---|---|---|
| `poke` | Held | Limited by worker_concurrency | None | Dev/short waits only |
| `reschedule` | Released between pokes | Unlimited | None | Production default |
| `deferrable` | Zero | Unlimited | Triggerer component | K8s/large-scale |

---

## Database Maintenance

```bash
# Clean old records (run as scheduled DAG or cron)
airflow db clean \
  --clean-before-timestamp "$(date -d '-90 days' --iso-8601=seconds)" \
  --tables task_instance,dag_run,xcom,log \
  --yes

# Check DB connectivity and version
airflow db check

# Run migrations after upgrade
airflow db migrate
```

---

## Tuning Checklist

**Scheduler:**
- [ ] `min_file_process_interval` set to 300+ (not default 30)
- [ ] `parsing_processes` set to CPU count - 1
- [ ] `max_active_runs_per_dag` ≤ 5 (prevents catchup flood)
- [ ] `standalone_dag_processor = True` (Airflow 3)

**Workers:**
- [ ] `worker_concurrency` tuned for task type (lower for CPU-heavy)
- [ ] `parallelism` ≥ (workers × worker_concurrency)
- [ ] All sensors use `mode="reschedule"` or `deferrable=True`

**Code:**
- [ ] No `Variable.get()` / `Connection.get()` at DAG module level
- [ ] No heavy imports (pandas, numpy) at module level
- [ ] DAG factory pattern used for similar DAGs
- [ ] No expensive top-level function calls

**Database:**
- [ ] PostgreSQL (not MySQL/SQLite)
- [ ] `airflow db clean` runs weekly
- [ ] `sql_alchemy_pool_recycle = 1800` set
- [ ] `autovacuum` tuned on `task_instance` table

**Monitoring:**
- [ ] StatsD metrics configured
- [ ] Alert on `scheduler_loop_duration` > 10s
- [ ] Alert on `tasks.starving` > 0 sustained
- [ ] DAG parsing duration alerts configured

---

## Anti-Patterns to Avoid

| Anti-Pattern | Impact | Fix |
|---|---|---|
| `Variable.get()` at module level | DB hit on every DAG parse | Move inside task callable |
| `poke` mode sensors | Worker slot waste | Use `reschedule` or `deferrable` |
| Many nearly-identical DAG files | Excessive parse time | Use DAG factory pattern |
| `max_active_runs_per_dag = 16` default with catchup | Queue flood | Set to 3–5 |
| No `airflow db clean` scheduled | Growing DB → slow queries | Schedule weekly cleanup |
| Heavy imports at module level | Slow parse times | Import inside functions |
| `min_file_process_interval = 30` in prod | Constant re-parsing | Set to 300+ |
| MySQL as metadata DB | Deadlocks, slow queries | Migrate to PostgreSQL |
| Very large `expand()` mapped tasks | Thousands of TI rows | Chunk your input |
| No pool limits on expensive tasks | Resource contention | Assign pools to heavy tasks |

---

## Quick Diagnosis Commands

```bash
# View current scheduler stats
airflow scheduler --num-runs 1 --subdir /dev/null 2>&1 | grep -E "(heartbeat|parsing|duration)"

# Count DAGs and tasks
airflow dags list | wc -l
airflow tasks list <dag_id> | wc -l

# Check for stuck tasks
airflow tasks states-for-dag-run <dag_id> <run_id>

# Show queued tasks count
airflow tasks list --dag-id <dag_id>

# Check pool usage
airflow pools list
```

---

## Pool Management

```bash
# Create a pool
airflow pools set warehouse_heavy 5 "Slow warehouse queries"

# View pool utilization
airflow pools list

# Import multiple pools from JSON
airflow pools import pools.json
```

```json
// pools.json
[
    {"name": "warehouse_heavy", "slots": 5, "description": "Heavy warehouse queries"},
    {"name": "external_api", "slots": 10, "description": "Rate-limited API"},
    {"name": "gpu_tasks", "slots": 2, "description": "GPU-intensive ML tasks"}
]
```
