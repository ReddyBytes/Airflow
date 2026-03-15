# 11 · Pools & Resources — Cheatsheet

---

## Pool Parameters — Quick Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pool` | `str` | `"default_pool"` | Name of the pool to assign the task to |
| `pool_slots` | `int` | `1` | Number of pool slots this task consumes |
| `priority_weight` | `int` | `1` | Queue priority — higher runs first |
| `queue` | `str` | `"default"` | Celery queue to route the task to (CeleryExecutor only) |

---

## Pool Slot States (Visible in UI)

| Column in UI | Meaning |
|---|---|
| **Slots** | Total configured slots in the pool |
| **Running** | Tasks currently occupying a slot and executing |
| **Queued** | Tasks assigned to the pool that are waiting for a slot |
| **Scheduled** | Tasks that are scheduled but not yet in the queue |
| **Open** | Available slots = Slots - Running |

---

## CLI Commands

```bash
# Create (or update) a pool
airflow pools set <pool_name> <num_slots> "<description>"
airflow pools set db_pool 5 "Max 5 concurrent DB connections"

# Get a single pool's details
airflow pools get db_pool

# List all pools
airflow pools list

# Delete a pool
airflow pools delete db_pool

# Import pools from JSON file (bulk creation)
airflow pools import /path/to/pools.json

# Export all pools to JSON
airflow pools export /path/to/output.json
```

**pools.json format:**

```json
{
  "db_pool":  { "slots": 5,  "description": "Database connections" },
  "api_pool": { "slots": 10, "description": "External API rate limit" },
  "ml_pool":  { "slots": 2,  "description": "ML training tasks" }
}
```

---

## Assigning a Task to a Pool

```python
from airflow.operators.python import PythonOperator

task = PythonOperator(
    task_id="my_task",
    python_callable=my_function,
    pool="db_pool",          # Pool name (must exist in Airflow)
    pool_slots=1,            # Slots consumed by this task
    priority_weight=5,       # Higher = runs sooner when competing
    queue="default",         # Celery queue (optional)
)
```

---

## priority_weight — How It Works

```
Pool: db_pool (5 slots, all occupied)

Waiting tasks:
  - bulk_export     priority_weight=1   ← runs last
  - standard_query  priority_weight=5   ← runs second
  - critical_report priority_weight=10  ← runs first

When a slot frees: critical_report enters first, then standard_query, then bulk_export
```

**Rules:**
- Higher number = higher priority.
- Ties are broken by scheduled time (older = higher priority).
- Default is `1` for all tasks.

---

## When to Use Pools vs Other Concurrency Controls

| You want to... | Use this |
|----------------|---------|
| Limit tasks talking to a **specific database** | `pool` on those tasks |
| Limit tasks calling a **specific API** | `pool` on those tasks |
| Limit total tasks in **one DAG** | `max_active_tasks_per_dag` in DAG definition |
| Limit total concurrent tasks **across all DAGs** | `parallelism` in `airflow.cfg` |
| Limit concurrent **DAG runs** (not tasks) | `max_active_runs_per_dag` in DAG definition |
| Route tasks to **specific workers** (Celery) | `queue` parameter |
| Prevent a resource-heavy task from running in parallel with itself | `pool` with `slots=1` |

---

## Real-World Pool Sizing Guide

| Resource | Typical Limit | Suggested Pool Slots |
|----------|--------------|----------------------|
| PostgreSQL (small RDS) | 100 connections | 10–20 |
| MySQL (medium) | 150 connections | 15–25 |
| REST API (free tier) | 10 req/min | 2–3 |
| REST API (paid tier) | 60 req/min | 10 |
| ML training (16GB RAM worker) | 1 model at a time | 1–2 |
| Snowflake (standard warehouse) | 8 concurrent queries | 6–8 |

---

## 📂 Navigation

⬅️ **Prev:** [Theory](./Theory.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Interview Q&A](./Interview_QA.md)
