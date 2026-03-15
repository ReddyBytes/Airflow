# 03 · DAGs Deep Dive — Cheatsheet

Quick reference for DAG parameters, schedules, states, and patterns.

---

## DAG Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dag_id` | str | Required | Unique name shown in UI and logs |
| `start_date` | datetime | Required | Date of the first interval. Must be static. |
| `schedule_interval` | str / timedelta / None | None | How often the DAG runs |
| `catchup` | bool | `True` | Backfill missed intervals since start_date |
| `default_args` | dict | `{}` | Task-level defaults (owner, retries, email, etc.) |
| `description` | str | `""` | Description shown in UI |
| `tags` | list[str] | `[]` | Filter tags in UI |
| `max_active_runs` | int | `16` | Max concurrent runs of this DAG |
| `max_active_tasks` | int | `16` | Max concurrent task instances across all runs |
| `on_failure_callback` | callable | None | Called when any task in the DAG fails |
| `on_success_callback` | callable | None | Called when the DAG run completes successfully |
| `dagrun_timeout` | timedelta | None | Cancel the run if it exceeds this duration |
| `is_paused_upon_creation` | bool | Config-driven | Whether DAG starts paused |
| `params` | dict | `{}` | Runtime parameters (for triggered runs) |

---

## default_args Keys

```python
default_args = {
    "owner": "your-team",           # Owner shown in UI
    "retries": 2,                   # How many times to retry on failure
    "retry_delay": timedelta(minutes=5),  # Wait between retries
    "email": ["alerts@company.com"],      # Alert recipients
    "email_on_failure": True,             # Email on task failure
    "email_on_retry": False,              # Email on each retry
    "depends_on_past": False,             # Task needs yesterday's instance to succeed
    "execution_timeout": timedelta(hours=2),  # Kill task after this duration
    "sla": timedelta(hours=1),            # Alert if task takes longer than this
}
```

---

## schedule_interval — Common Examples

### Preset Aliases

| Alias | Cron Equivalent | Meaning |
|-------|----------------|---------|
| `@once` | — | Run exactly once |
| `@hourly` | `0 * * * *` | Every hour at :00 |
| `@daily` | `0 0 * * *` | Every midnight |
| `@weekly` | `0 0 * * 0` | Every Sunday midnight |
| `@monthly` | `0 0 1 * *` | 1st of each month, midnight |
| `@yearly` | `0 0 1 1 *` | Jan 1st midnight |
| `None` | — | Manual trigger only |

### Cron Format

```
┌───────── minute (0–59)
│ ┌─────── hour (0–23)
│ │ ┌───── day of month (1–31)
│ │ │ ┌─── month (1–12)
│ │ │ │ ┌─ day of week (0=Sun, 6=Sat)
│ │ │ │ │
* * * * *
```

### Custom Cron Examples

| Expression | Meaning |
|------------|---------|
| `0 6 * * *` | 6:00am every day |
| `0 6 * * 1-5` | 6:00am Monday–Friday |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1,15 * *` | Midnight on 1st and 15th of month |
| `0 8-18 * * 1-5` | Every hour from 8am–6pm, weekdays only |
| `0 0 * * 0` | Every Sunday at midnight |

---

## Task Dependency Operators

```python
# Forward dependency (A runs before B)
task_a >> task_b

# Backward dependency (equivalent)
task_b << task_a

# Chain: A → B → C
task_a >> task_b >> task_c

# Fan-out: A triggers B and C in parallel
task_a >> [task_b, task_c]

# Fan-in: D only runs after both B and C succeed
[task_b, task_c] >> task_d

# Diamond pattern: A → B,C → D
task_a >> [task_b, task_c]
[task_b, task_c] >> task_d

# Method equivalents
task_b.set_upstream(task_a)      # same as task_a >> task_b
task_a.set_downstream(task_b)    # same as task_a >> task_b

# Cross-dependency helper
from airflow.models.baseoperator import cross_downstream
cross_downstream([task_a, task_b], [task_c, task_d])
# Creates: a>>c, a>>d, b>>c, b>>d
```

---

## DAG Run States

| State | Meaning |
|-------|---------|
| `queued` | Created but not yet evaluated |
| `running` | At least one task is running or scheduled |
| `success` | All tasks finished successfully |
| `failed` | At least one task failed (with no retries left) |
| `dataset_triggered` | Triggered by a dataset update |

---

## Task Instance States

| State | Meaning |
|-------|---------|
| `none` | Not yet considered for scheduling |
| `scheduled` | Scheduler decided it should run |
| `queued` | Executor has it, waiting for a worker slot |
| `running` | Worker is executing it |
| `success` | Completed without error |
| `failed` | Raised an exception, no retries left |
| `up_for_retry` | Failed, has retries remaining |
| `up_for_reschedule` | Sensor in reschedule mode, waiting |
| `skipped` | BranchOperator or ShortCircuit chose a different path |
| `upstream_failed` | An upstream task failed; this one will not run |
| `removed` | Task was removed from the DAG after the run started |
| `restarting` | Task was requested to restart |

---

## Common DAG Patterns

### Linear ETL

```python
extract >> transform >> load >> notify
```

### Fan-Out (Parallel Processing)

```python
extract >> [transform_region_a, transform_region_b, transform_region_c]
[transform_region_a, transform_region_b, transform_region_c] >> merge
merge >> load
```

### Start / End Sentinels

```python
from airflow.operators.empty import EmptyOperator

start = EmptyOperator(task_id="start")
end   = EmptyOperator(task_id="end")

start >> [task_a, task_b, task_c] >> end
```

### Parametrized with Variables

```python
from airflow.models import Variable

env = Variable.get("environment", default_var="dev")
```

---

## Template Variables (Jinja)

Use inside `bash_command`, SQL strings, or any templated field:

| Template | Value |
|----------|-------|
| `{{ ds }}` | Logical date as `YYYY-MM-DD` |
| `{{ ds_nodash }}` | Logical date as `YYYYMMDD` |
| `{{ ts }}` | ISO 8601 timestamp |
| `{{ dag.dag_id }}` | The DAG's ID |
| `{{ task.task_id }}` | The task's ID |
| `{{ run_id }}` | The DAG Run ID |
| `{{ var.value.my_var }}` | Value of Airflow Variable `my_var` |
| `{{ conn.my_conn.host }}` | Host from Airflow Connection `my_conn` |

---

## 📂 Navigation

⬅️ **Prev:** [Theory](./Theory.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Interview Q&A](./Interview_QA.md)
