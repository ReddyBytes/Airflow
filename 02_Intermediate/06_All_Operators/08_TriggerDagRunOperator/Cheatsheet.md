# TriggerDagRunOperator — Cheatsheet

> Quick reference for Apache Airflow 3. Core package — no extra provider needed.

---

## Import

```python
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
```

No additional `pip install` required — TriggerDagRunOperator ships with `apache-airflow` core.

---

## Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trigger_dag_id` | `str` | required | DAG ID of the DAG to trigger |
| `conf` | `dict` | `None` | JSON-serialisable config passed to the triggered DAG run |
| `logical_date` | `str \| datetime` | current time | Logical date for the triggered DAG run (Airflow 3); `execution_date` in Airflow 2 |
| `reset_dag_run` | `bool` | `False` | Clear and re-run if a run for this date already exists |
| `wait_for_completion` | `bool` | `False` | Block until the triggered DAG run reaches a terminal state |
| `poke_interval` | `int` | `60` | Seconds between status polls (used with `wait_for_completion=True`) |
| `allowed_states` | `list[str]` | `["success"]` | Triggered DAG states considered as "this task succeeded" |
| `failed_states` | `list[str]` | `["failed"]` | Triggered DAG states that fail this task |
| `trigger_run_id` | `str` | `None` | Custom run ID for the triggered DAG run |
| `deferrable` | `bool` | `False` | Use async polling (frees worker slot while waiting) |

---

## Code Patterns

### Basic Trigger (Fire and Forget)

```python
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

trigger = TriggerDagRunOperator(
    task_id="trigger_transform",
    trigger_dag_id="transform_dag",    # must match dag_id exactly
)
# Does NOT wait — marks itself succeeded immediately after triggering
```

### Trigger with Configuration

```python
TriggerDagRunOperator(
    task_id="trigger_with_conf",
    trigger_dag_id="transform_dag",
    conf={
        "batch_date": "{{ ds }}",
        "source_table": "raw_orders",
        "row_count": "{{ ti.xcom_pull(task_ids='count_rows') }}",
    },
)
```

```python
# In the triggered DAG, read conf:
def process(**context):
    conf = context["dag_run"].conf
    batch_date = conf.get("batch_date", "unknown")
    source_table = conf.get("source_table", "default_table")
```

### Trigger and Wait for Completion

```python
TriggerDagRunOperator(
    task_id="trigger_and_wait",
    trigger_dag_id="critical_pipeline",
    wait_for_completion=True,
    poke_interval=30,               # poll every 30 seconds
    allowed_states=["success"],
    failed_states=["failed", "upstream_failed"],
    timeout=timedelta(hours=2),     # give up after 2 hours
)
```

### Trigger and Wait — Deferrable Mode (Recommended for Long Waits)

```python
TriggerDagRunOperator(
    task_id="trigger_long_dag",
    trigger_dag_id="long_running_dag",
    wait_for_completion=True,
    deferrable=True,           # free worker slot while polling
    poke_interval=60,
    allowed_states=["success"],
    failed_states=["failed"],
)
```

### Trigger with Reset (Safe Re-runs)

```python
TriggerDagRunOperator(
    task_id="trigger_with_reset",
    trigger_dag_id="transform_dag",
    logical_date="{{ ds }}",    # same logical date as the parent
    reset_dag_run=True,         # clear existing run for this date and re-trigger
    wait_for_completion=True,
)
```

### Trigger Multiple Child DAGs in Parallel

```python
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

trigger_region_a = TriggerDagRunOperator(
    task_id="trigger_region_a",
    trigger_dag_id="process_region_a",
    conf={"region": "us-east-1"},
)

trigger_region_b = TriggerDagRunOperator(
    task_id="trigger_region_b",
    trigger_dag_id="process_region_b",
    conf={"region": "eu-west-1"},
)

# No dependency between them — they trigger in parallel
trigger_region_a
trigger_region_b
```

### Trigger with Failure Alert

```python
from datetime import timedelta

def alert_on_failure(context):
    print(f"Child DAG failed: {context['task_instance']}")
    # send Slack message, PagerDuty alert, etc.

TriggerDagRunOperator(
    task_id="trigger_critical",
    trigger_dag_id="critical_dag",
    wait_for_completion=True,
    failed_states=["failed"],
    retries=2,
    retry_delay=timedelta(minutes=15),
    on_failure_callback=alert_on_failure,
)
```

---

## SubDag vs TriggerDagRunOperator vs TaskGroup

| Approach | Status | Use Case |
|----------|--------|----------|
| **SubDagOperator** | Deprecated / Removed in Airflow 3 | Never use |
| **TaskGroup** | Recommended | Organise tasks visually within one DAG |
| **TriggerDagRunOperator** | Recommended | DAG-to-DAG dependencies, cross-team orchestration |

**Rule of thumb**: If the tasks belong to the same pipeline and same team, use TaskGroup. If they belong to separately managed/scheduled DAGs, use TriggerDagRunOperator.

---

## Worker Slot Impact

| Configuration | Worker Slot Behaviour |
|---------------|----------------------|
| `wait_for_completion=False` | Slot released immediately after trigger |
| `wait_for_completion=True, deferrable=False` | Slot held for the entire duration of the triggered DAG |
| `wait_for_completion=True, deferrable=True` | Slot released; Triggerer process polls asynchronously |

Always use `deferrable=True` when waiting for DAGs that run for more than a few minutes.

---

## When to Use TriggerDagRunOperator

- Cross-team pipelines where DAGs are owned by different teams.
- Reusable DAGs triggered by multiple parent DAGs.
- Fan-out orchestration: one parent DAG launching multiple child DAGs.
- Separating concerns: ingestion DAG triggers transformation DAG on success.
- On-demand child pipeline runs (e.g., triggering a model retrain when new data arrives).

## When to Avoid TriggerDagRunOperator

- Simple task dependencies within one team's pipeline — use TaskGroup instead.
- When you need tight XCom communication between tasks — TriggerDagRunOperator only passes `conf` (a flat dict), not rich typed objects.
- Avoid creating deep chains (A triggers B triggers C triggers D) — debugging failures across 4+ DAG levels is painful.
- Never use it to create circular dependencies.

---

## Golden Rules

1. **Use `deferrable=True`** when `wait_for_completion=True` for long-running child DAGs — never block a worker slot for hours.
2. **Always set `failed_states`** when using `wait_for_completion=True` — otherwise failures in the child DAG are silently ignored.
3. **Use `reset_dag_run=True`** in backfill/re-run scenarios to avoid `DagRunAlreadyExists` errors.
4. **Keep `conf` payloads small and flat** — it is not a data transport layer; it is for config parameters.
5. **Document inter-DAG dependencies** in a central registry or diagram — they are invisible to Airflow's dependency graph UI.
6. **Never create circular DAG triggers** — Airflow does not detect them automatically.
7. **Pin `trigger_dag_id` values** — if the target DAG is renamed, the trigger silently breaks at runtime.
8. **Test child DAGs independently** before adding TriggerDagRunOperator — a broken child DAG causes failures that look like operator problems.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev operator** | [07_KubernetesPodOperator](../07_KubernetesPodOperator/) |
| **Section root** | [02_Intermediate](../../) |
