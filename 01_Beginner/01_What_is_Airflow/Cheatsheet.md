# 01 · Core Concepts — Cheatsheet

Quick reference for everything in Section 01. Bookmark this page and return to it while building.

---

## Core Terminology

| Term | Plain English Definition |
|------|--------------------------|
| **Airflow** | Open-source workflow orchestration platform |
| **DAG** | Directed Acyclic Graph — a Python file defining a workflow |
| **Task** | One unit of work inside a DAG |
| **Operator** | Template/class used to create a task |
| **DAG Run** | One execution of a DAG for a specific logical date |
| **Task Instance** | One execution of a specific task within a DAG Run |
| **Schedule Interval** | How often a DAG runs (cron expression or preset) |
| **start_date** | The date from which Airflow begins scheduling the DAG |
| **Catchup** | Whether Airflow should run missed intervals from start_date until now |
| **XCom** | Cross-communication — small values passed between tasks |
| **Connection** | Stored credentials for external systems (DB, API, S3, etc.) |
| **Variable** | Key-value configuration stored in the Metadata DB |
| **Pool** | A named slot limit for controlling task parallelism |
| **SLA** | Service Level Agreement — max allowed time for a task to complete |

---

## Component Responsibilities

| Component | Job | Breaks If Missing |
|-----------|-----|------------------|
| **Scheduler** | Reads DAGs, creates runs, submits tasks to Executor | Nothing runs |
| **Webserver** | Serves the UI dashboard | Cannot see status (pipelines still run) |
| **Metadata Database** | Stores all state, history, config | Everything breaks |
| **Executor** | Determines how/where tasks run | Tasks never execute |
| **Worker** | Actually runs the task code | Tasks never execute |
| **Triggerer** | Handles deferrable (async waiting) tasks | Deferrable tasks hang |

---

## Airflow vs Cron vs Luigi

| Feature | Cron | Luigi | Airflow |
|---------|------|-------|---------|
| Task dependencies | No | Yes | Yes |
| UI dashboard | No | Basic | Full |
| Automatic retries | No | Partial | Yes |
| Backfilling | No | No | Yes |
| Scalable workers | No | Limited | Yes (CeleryExecutor, K8s) |
| Defined in code | Shell scripts | Python | Python |
| Community & plugins | Small | Small | Very large |
| Managed cloud options | No | No | MWAA, Composer, Astronomer |

---

## Key Configuration Parameters

| Parameter | Where Set | Default | Purpose |
|-----------|-----------|---------|---------|
| `AIRFLOW_HOME` | Env variable | `~/airflow` | Root folder for Airflow files |
| `dags_folder` | `airflow.cfg` | `$AIRFLOW_HOME/dags` | Where Scheduler looks for DAG files |
| `executor` | `airflow.cfg` | `SequentialExecutor` | Which executor to use |
| `sql_alchemy_conn` | `airflow.cfg` | SQLite path | Metadata Database connection string |
| `dag_dir_list_interval` | `airflow.cfg` | `300` (seconds) | How often Scheduler scans for new DAGs |
| `min_file_process_interval` | `airflow.cfg` | `30` (seconds) | How often a DAG file is re-parsed |
| `max_active_runs_per_dag` | `airflow.cfg` | `16` | Max concurrent runs for a single DAG |

---

## DAG File Skeleton

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="my_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
) as dag:

    task_a = BashOperator(task_id="task_a", bash_command="echo A")
    task_b = BashOperator(task_id="task_b", bash_command="echo B")

    task_a >> task_b   # task_b runs after task_a
```

---

## Task Instance States

| State | Meaning |
|-------|---------|
| `none` | Not yet queued |
| `scheduled` | Scheduler has decided it should run |
| `queued` | Executor has accepted it, waiting for a worker |
| `running` | Worker is executing it now |
| `success` | Completed without error |
| `failed` | Raised an exception |
| `up_for_retry` | Failed but has retries remaining |
| `up_for_reschedule` | Sensor waiting in reschedule mode |
| `skipped` | Upstream branch did not choose this path |
| `upstream_failed` | An upstream task failed; this one will not run |

---

## Golden Rules

1. **DAG files are parsed every ~30 seconds.** Never put slow code at the top level of a DAG file.
2. **start_date must be static.** Never use `datetime.now()` as start_date.
3. **Airflow is not a data processor.** It orchestrates — use Spark, pandas, or SQL for actual transformation.
4. **Tasks must be idempotent.** Running a task twice should produce the same result as running it once.
5. **Use catchup=False unless you need backfilling.** Otherwise new DAGs will immediately create dozens of historical runs.

---

## 📂 Navigation

⬅️ **Prev:** [Theory](./Theory.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Interview Q&A](./Interview_QA.md)
