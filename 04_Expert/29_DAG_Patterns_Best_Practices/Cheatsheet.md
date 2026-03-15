# 29 — DAG Patterns and Best Practices: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Pattern Summary Table

| Pattern | Problem It Solves | Key Implementation |
|---|---|---|
| **Idempotency** | Duplicate data on retry | DELETE + INSERT, upsert, overwrite partitions |
| **Atomic Writes** | Partial/corrupt output | Write to `.tmp` file, rename on success |
| **Backfill Safety** | Can't replay historical runs | Use `{{ ds }}` not `datetime.now()` |
| **Avoid Top-Level Code** | Slow DAG parsing, DB overload | Move all calls inside task functions |
| **DAG Factory** | Copy-paste duplication, slow parsing | `for config in configs: make_dag(config)` |
| **Fan-Out / Fan-In** | Parallel processing with aggregation | Tasks expand + `trigger_rule="all_success"` |
| **Config-Driven DAGs** | DAG logic mixed with configuration | YAML/JSON config + factory function |
| **Versioning** | Breaking changes mid-flight | `dag_id="my_dag_v2"` for breaking changes |
| **Documentation** | DAGs nobody understands | `doc_md` on DAG and tasks |
| **Pool Limits** | Resource exhaustion | `pool="heavy_pool"`, `pool_slots=1` |

---

## Idempotency Patterns

```python
# Pattern 1: DELETE + INSERT (SQL)
engine.execute(f"DELETE FROM table WHERE date = '{ds}'")
df.to_sql("table", engine, if_exists="append")

# Pattern 2: UPSERT
df.to_sql("table_staging", engine, if_exists="replace")
engine.execute("""
    INSERT INTO table SELECT * FROM table_staging
    ON CONFLICT (id) DO UPDATE SET col = EXCLUDED.col
""")

# Pattern 3: Partition overwrite (Spark/BigQuery)
df.write.mode("overwrite").partitionBy("date").parquet(f"s3://bucket/{ds}/")

# Pattern 4: S3 key deterministic naming
s3.put_object(
    Bucket="my-bucket",
    Key=f"data/{ds}/output.parquet",   # Same key every run = overwrites
    Body=data,
)
```

---

## Atomic Write Patterns

```python
# Local file
import os
tmp = f"{output_path}.tmp.{os.getpid()}"
write_data(tmp)
os.replace(tmp, output_path)          # Atomic on POSIX

# S3 (uploads are atomic — obj appears only when complete)
s3.upload_file(local_file, bucket, key)

# Database transaction
with engine.begin() as conn:          # Commits on exit, rolls back on exception
    conn.execute("DELETE FROM t WHERE dt = :dt", {"dt": ds})
    conn.execute("INSERT INTO t ...", rows)
    # Both ops committed atomically
```

---

## Anti-Patterns List

| Anti-Pattern | Why Bad | Fix |
|---|---|---|
| `datetime.now()` in tasks | Can't backfill | Use `context["logical_date"]` |
| `Variable.get()` at module level | DB call on every parse | Move inside task function |
| `import pandas` at module level | Slow parse for every scheduler cycle | Import inside task functions |
| `mode="poke"` sensors | Worker slot waste | Use `mode="reschedule"` |
| `if_exists="append"` without DELETE | Duplicate data on retry | DELETE first, or use upsert |
| Write directly to final path | Partial files on failure | Write to `.tmp`, rename |
| Many nearly-identical DAG files | Parse overhead, duplication | DAG factory pattern |
| No `doc_md` or description | Undocumentable pipeline | Add `doc_md` to every DAG |
| `max_active_runs_per_dag=16` with catchup | Queue flood on unpausing | Set to 3–5 |
| `depends_on_past=True` without understanding it | Blocks all future runs on failure | Use deliberately, document why |
| XCom for large data | Metadata DB bloat | Push to S3, pass S3 URI in XCom |

---

## DAG Factory Template

```python
# Minimal factory pattern
CONFIGS = [
    {"dag_id": "etl_orders", "schedule": "@daily", "table": "orders"},
    {"dag_id": "etl_customers", "schedule": "0 5 * * *", "table": "customers"},
]

def make_dag(cfg: dict):
    with DAG(dag_id=cfg["dag_id"], schedule=cfg["schedule"], ...) as dag:
        # Build tasks using cfg values
        ...
    return dag

# Must register in globals() for Airflow to discover
for _cfg in CONFIGS:
    _dag = make_dag(_cfg)
    globals()[_dag.dag_id] = _dag
```

---

## DAG Quality Checklist

**Design:**
- [ ] Every task is idempotent (safe to re-run)
- [ ] No `datetime.now()` — always uses `{{ ds }}` or `logical_date`
- [ ] Write to staging/tmp first, rename/commit on success
- [ ] Designed to work for backfills (historical execution dates)

**Code Quality:**
- [ ] No `Variable.get()` / `Connection.get()` at module level
- [ ] No heavy imports at module level (pandas, numpy, etc.)
- [ ] No DB queries or network calls at module level
- [ ] Static configuration only at module level

**Concurrency:**
- [ ] `max_active_runs` appropriate for the DAG (not unlimited)
- [ ] Expensive tasks assigned to a pool
- [ ] Sensors using `mode="reschedule"` (not `poke`)
- [ ] No XCom with large data (>100KB) — use S3/GCS references instead

**Documentation:**
- [ ] DAG has `doc_md` with: purpose, owner, Slack/PagerDuty, runbook link
- [ ] Tasks have `doc_md` for non-obvious steps
- [ ] DAG has `description` field filled in
- [ ] `tags` applied for filtering (team name, data domain, criticality)

**Operations:**
- [ ] `default_args["retries"]` set (at least 1)
- [ ] `default_args["retry_delay"]` set
- [ ] `catchup` explicitly set (`False` unless backfilling is intended)
- [ ] `email_on_failure` configured (or `on_failure_callback`)
- [ ] `sla` set for SLA-sensitive pipelines

---

## Trigger Rule Reference

| `trigger_rule` | Triggers when... | Use Case |
|---|---|---|
| `all_success` | All upstream succeeded | Default — standard sequential pipeline |
| `all_failed` | All upstream failed | Cleanup/rollback on failure |
| `all_done` | All upstream done (any state) | Always-run finalization |
| `one_success` | At least one upstream succeeded | Fan-in that tolerates partial failure |
| `one_failed` | At least one upstream failed | Alert task in parallel pipeline |
| `none_failed` | No upstream failed (success or skipped OK) | After optional branching |
| `none_skipped` | No upstream skipped | When branch skips must block |

---

## XCom Size Guidelines

| Data | Strategy |
|---|---|
| Small values (<1 KB): string, int, bool, small dict | Use XCom directly |
| Medium values (1–100 KB): small DataFrames, lists | Use XCom (monitor DB) |
| Large values (>100 KB): DataFrames, files | Write to S3/GCS, push URI to XCom |
| Files | Never push file contents to XCom — push S3/GCS path |
