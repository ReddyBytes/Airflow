# ExternalTaskSensor — Cheatsheet

## Quick Reference: Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `external_dag_id` | `str` | required | `dag_id` of the DAG to wait for |
| `external_task_id` | `str \| None` | required | `task_id` to wait for. `None` = wait for entire DAG run |
| `allowed_states` | `list[str]` | `["success"]` | States that count as "done — proceed" |
| `failed_states` | `list[str]` | `None` | States that cause the sensor to fail immediately |
| `execution_delta` | `timedelta` | `None` | Fixed offset from current execution date to look for |
| `execution_date_fn` | `Callable` | `None` | Function: `(dt) -> datetime | list[datetime]`. For complex date logic. |
| `poke_interval` | `float` | `60` | Seconds between each metadata DB check |
| `timeout` | `float` | `604800` | Max seconds before task fails or skips |
| `mode` | `str` | `"poke"` | `"poke"` (hold worker) or `"reschedule"` (free worker) |
| `soft_fail` | `bool` | `False` | Skip instead of fail on timeout |
| `check_existence` | `bool` | `False` | Fail immediately if the external DAG/task doesn't exist |
| `deferrable` | `bool` | `False` | Use async trigger (Airflow 2.7+, efficient for long waits) |

---

## Import

```python
from airflow.sensors.external_task import ExternalTaskSensor
```

---

## Code Patterns

### Pattern 1: Wait for a Specific Task (Same Schedule)

Both DAGs run on the same schedule — execution dates match automatically.

```python
from airflow.sensors.external_task import ExternalTaskSensor

ExternalTaskSensor(
    task_id="wait_for_upstream_load",
    external_dag_id="data_ingestion_pipeline",
    external_task_id="load_to_warehouse",
    allowed_states=["success"],
    failed_states=["failed", "upstream_failed"],
    poke_interval=60,
    timeout=2 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 2: Wait for an Entire DAG Run to Complete

```python
ExternalTaskSensor(
    task_id="wait_for_full_pipeline",
    external_dag_id="upstream_etl_pipeline",
    external_task_id=None,   # None = wait for entire DAG
    allowed_states=["success"],
    failed_states=["failed"],
    poke_interval=120,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 3: Different Schedules — Using execution_delta

DAG A runs hourly. DAG B runs daily at midnight. DAG B waits for DAG A's 11pm run.

```python
from datetime import timedelta

ExternalTaskSensor(
    task_id="wait_for_last_hourly_run",
    external_dag_id="hourly_data_loader",
    external_task_id="load_complete",
    execution_delta=timedelta(hours=1),
    # DAG B exec date: 2024-01-15 00:00
    # Looks for DAG A exec date: 2024-01-14 23:00
    allowed_states=["success"],
    failed_states=["failed", "upstream_failed"],
    poke_interval=60,
    timeout=3 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 4: Complex Schedule — Using execution_date_fn

Wait for all 24 hourly runs of the day to complete.

```python
from datetime import timedelta

def get_all_hourly_runs_today(dt):
    """Return execution dates for all 24 hourly runs leading up to dt."""
    return [dt - timedelta(hours=h) for h in range(1, 25)]

ExternalTaskSensor(
    task_id="wait_for_all_hourly_loads",
    external_dag_id="hourly_data_loader",
    external_task_id="load_data",
    execution_date_fn=get_all_hourly_runs_today,
    allowed_states=["success"],
    poke_interval=120,
    timeout=6 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 5: Multiple Upstream DAGs in Parallel

```python
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator

wait_for_sales = ExternalTaskSensor(
    task_id="wait_for_sales_pipeline",
    external_dag_id="sales_ingestion",
    external_task_id=None,
    failed_states=["failed"],
    poke_interval=60, timeout=7200, mode="reschedule",
)

wait_for_inventory = ExternalTaskSensor(
    task_id="wait_for_inventory_pipeline",
    external_dag_id="inventory_ingestion",
    external_task_id=None,
    failed_states=["failed"],
    poke_interval=60, timeout=7200, mode="reschedule",
)

run_report = PythonOperator(task_id="run_combined_report", ...)

# Both sensors run in parallel
[wait_for_sales, wait_for_inventory] >> run_report
```

---

### Pattern 6: With failed_states for Fast Failure

Without `failed_states`, the sensor waits until timeout even if the upstream DAG already failed. Set `failed_states` to fail fast.

```python
ExternalTaskSensor(
    task_id="wait_for_upstream",
    external_dag_id="critical_pipeline",
    external_task_id="final_load",
    allowed_states=["success"],
    failed_states=["failed", "upstream_failed", "skipped"],
    poke_interval=60,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 7: Deferrable Mode (Airflow 2.7+ / 3.x)

Releases not just the worker slot but offloads the entire wait to the Triggerer process — most efficient for long waits.

```python
ExternalTaskSensor(
    task_id="wait_for_upstream",
    external_dag_id="data_pipeline",
    external_task_id="load_complete",
    deferrable=True,          # Use async triggerer
    poke_interval=60,
    timeout=4 * 60 * 60,
    allowed_states=["success"],
    failed_states=["failed"],
)
```

---

## Execution Date Matching Logic

```
Current DAG execution date: T

With no delta/fn:        Looks for external task at execution_date = T
With execution_delta:    Looks for external task at execution_date = T - execution_delta
With execution_date_fn:  Looks for external task at each date returned by fn(T)
```

**Quick diagnosis:** If the sensor is stuck, check the logs. It prints the execution date it's searching for. Then verify that execution date exists in the external DAG's task instances.

---

## State Reference

| State | Meaning |
|---|---|
| `success` | Task completed successfully |
| `failed` | Task failed |
| `upstream_failed` | Task was skipped because an upstream task failed |
| `skipped` | Task was intentionally skipped |
| `running` | Task is currently running |
| `queued` | Task is waiting for a worker |

For `allowed_states`, `"success"` is almost always the right choice.
For `failed_states`, use `["failed", "upstream_failed"]` at minimum.

---

## When to Use / Avoid

**Use ExternalTaskSensor when:**
- Two separately scheduled DAGs have a dependency between them
- You need to gate DAG B until DAG A's specific task or full run completes
- Different teams own different pipelines but share data dependencies
- The upstream DAG runs on a predictable schedule you can align to

**Avoid ExternalTaskSensor when:**
- The upstream DAG is manually triggered (execution dates are unpredictable) — use Datasets
- You want purely event-driven triggers — use Datasets (Airflow 2.4+)
- The upstream pipeline is external to Airflow entirely — use `HttpSensor` or `S3KeySensor` instead

---

## Golden Rules

1. **Always set `failed_states`** — without it, you wait until timeout even if upstream already failed.
2. **Use `mode="reschedule"` or `deferrable=True`** — never block a worker for hours waiting for another DAG.
3. **Verify execution date alignment** — wrong `execution_delta` is the #1 cause of sensors stuck forever.
4. **Set a realistic `timeout`** — default 7 days is too long; set it to match your upstream SLA + buffer.
5. **Set `check_existence=True` in CI/staging** — fails fast if the external DAG ID or task ID is mistyped.
6. **Use `external_task_id=None` cautiously** — it waits for ALL tasks in the DAG to succeed; skipped tasks in the upstream may block it.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview questions |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [HttpSensor](../02_HttpSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [S3KeySensor](../04_S3KeySensor/Theory.md)
