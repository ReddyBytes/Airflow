# TriggerDagRunOperator — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Beginner

**Q1. What is TriggerDagRunOperator and what problem does it solve?**

Imagine you have a large data pipeline split across two DAGs: `ingest_dag` loads raw data, and `transform_dag` processes it. You want `transform_dag` to start only after `ingest_dag` finishes — but they are separate DAGs managed by different teams. TriggerDagRunOperator is the Airflow-native way to trigger one DAG from inside another. It acts like a "remote control" for DAG execution, letting you chain DAGs together without merging them or writing scheduler hacks.

**Q2. When should you trigger another DAG instead of putting everything in one DAG?**

Good reasons to split into separate DAGs and use TriggerDagRunOperator:

- **Ownership**: Different teams own different pipeline stages.
- **Reusability**: A DAG is a reusable unit that multiple DAGs can trigger independently.
- **Scheduling independence**: Each DAG can run on its own schedule, but can also be triggered on demand.
- **Isolation**: A failure in one DAG does not cascade to unrelated tasks in a single monolithic DAG.
- **Parallel orchestration**: One parent DAG can trigger multiple child DAGs simultaneously.

**Q3. What is `trigger_dag_id`?**

`trigger_dag_id` is the DAG ID of the DAG you want to trigger. It must exactly match the `dag_id` defined in the target DAG file:

```python
TriggerDagRunOperator(
    task_id="trigger_transform",
    trigger_dag_id="transform_dag",   # must match dag_id in the target DAG
)
```

If the DAG ID does not exist in Airflow, the task will fail at runtime with a `DagNotFound` error.

**Q4. Does TriggerDagRunOperator wait for the triggered DAG to finish?**

By default, no. The operator triggers the DAG run and immediately marks itself as succeeded. The triggered DAG runs independently in the background. If you need to wait for completion, set `wait_for_completion=True` (covered in the Intermediate section).

**Q5. What happens if you trigger a DAG that is paused?**

Triggering a paused DAG will fail unless you set `deferrable=True` or handle it explicitly. By default, Airflow raises an error if you try to trigger a paused DAG. Best practice: ensure the target DAG is unpaused before depending on TriggerDagRunOperator in production.

---

## Intermediate

**Q6. How do you pass configuration data (conf) to the triggered DAG?**

Use the `conf` parameter, which accepts a dict. The triggered DAG can access it via `dag_run.conf`:

```python
# Triggering DAG
TriggerDagRunOperator(
    task_id="trigger_with_config",
    trigger_dag_id="transform_dag",
    conf={
        "batch_date": "{{ ds }}",
        "source_table": "raw_orders",
        "row_count": "{{ ti.xcom_pull(task_ids='count_rows') }}",
    },
)
```

```python
# Inside transform_dag, accessing the config:
def transform(**context):
    batch_date = context["dag_run"].conf.get("batch_date")
    source_table = context["dag_run"].conf.get("source_table")
    print(f"Processing {source_table} for {batch_date}")
```

`conf` is Jinja-templated, so you can inject execution dates, XCom values, and Airflow Variables.

**Q7. How do you wait for the triggered DAG to complete before continuing?**

Set `wait_for_completion=True`. The operator will poll the triggered DAG run's state until it reaches a terminal state (success or failure):

```python
TriggerDagRunOperator(
    task_id="trigger_and_wait",
    trigger_dag_id="transform_dag",
    wait_for_completion=True,
    poke_interval=30,           # poll every 30 seconds
    allowed_states=["success"], # states that mean "done successfully"
    failed_states=["failed"],   # states that should fail this task
)
```

With `wait_for_completion=True`, the triggering task stays `running` until the triggered DAG finishes. This blocks a worker slot for the entire duration.

**Q8. What are `allowed_states` and `failed_states`?**

These parameters define what outcome of the triggered DAG run is considered a pass or fail for the TriggerDagRunOperator task:

- `allowed_states`: DAG run states that mark the TriggerDagRunOperator as **succeeded**. Default: `["success"]`.
- `failed_states`: DAG run states that mark the TriggerDagRunOperator as **failed**. Default: `["failed"]`.

You can customise these for workflows where you consider `skipped` or `queued` states acceptable:

```python
TriggerDagRunOperator(
    task_id="trigger_optional_dag",
    trigger_dag_id="optional_cleanup_dag",
    wait_for_completion=True,
    allowed_states=["success", "skipped"],
    failed_states=["failed", "upstream_failed"],
)
```

**Q9. What is `reset_dag_run` and when do you need it?**

`reset_dag_run=True` tells Airflow to clear (reset) the triggered DAG run if it already exists for the same logical date, rather than creating a duplicate. Use this in re-run scenarios: if the parent DAG is re-triggered for a historical date, you want the child DAG to also re-run, not skip because a run already exists.

```python
TriggerDagRunOperator(
    task_id="trigger_transform",
    trigger_dag_id="transform_dag",
    reset_dag_run=True,           # clear existing run for this date, then re-run
    wait_for_completion=True,
)
```

Without `reset_dag_run=True`, Airflow raises a `DagRunAlreadyExists` exception if a run for that execution date already exists.

**Q10. Can you pass the execution date to the triggered DAG?**

Yes, use `logical_date` (Airflow 3) or `execution_date` (Airflow 2 compatibility) to specify the logical date of the triggered run:

```python
from airflow.utils import timezone

TriggerDagRunOperator(
    task_id="trigger_backfill",
    trigger_dag_id="transform_dag",
    logical_date="{{ ds }}",         # trigger for the same logical date as the parent
)
```

If not specified, the triggered DAG run uses the current timestamp as its logical date.

---

## Advanced

**Q11. SubDag vs TriggerDagRunOperator vs TaskGroup — what should you choose?**

| Approach | What it is | When to use | When to avoid |
|----------|-----------|-------------|---------------|
| **SubDagOperator** | Deprecated pattern embedding a DAG inside a task | Never — deprecated in Airflow 2.0, removed in Airflow 3 | Always avoid |
| **TriggerDagRunOperator** | Triggers a separately scheduled/managed DAG | Cross-team DAG dependencies, reusable DAGs, complex orchestration | Simple task grouping within one team's pipeline |
| **TaskGroup** | Visual grouping of tasks within one DAG | Organising related tasks in the same DAG, same team | When tasks genuinely belong in separate DAGs |

The modern recommendation: use TaskGroups for in-DAG organisation and TriggerDagRunOperator for DAG-to-DAG orchestration. Forget SubDagOperator exists.

**Q12. How do you handle failures in the triggered DAG?**

When `wait_for_completion=True`, the TriggerDagRunOperator will fail if the triggered DAG run reaches a state listed in `failed_states`. From there, standard Airflow task failure handling applies:

1. **Retries**: Set `retries` on the TriggerDagRunOperator — it will re-trigger the child DAG on retry.
2. **`on_failure_callback`**: Trigger an alert (Slack, PagerDuty) when the child DAG fails.
3. **Manual handling**: Use `failed_states=[]` to make TriggerDagRunOperator always succeed regardless of the child outcome (risky — use carefully).

```python
TriggerDagRunOperator(
    task_id="trigger_critical_dag",
    trigger_dag_id="critical_transform",
    wait_for_completion=True,
    failed_states=["failed", "upstream_failed"],
    retries=2,
    retry_delay=timedelta(minutes=10),
    on_failure_callback=send_alert_to_slack,
)
```

**Q13. How do circular dependencies work and how do you avoid them?**

A circular dependency occurs when DAG A triggers DAG B, and DAG B (directly or transitively) triggers DAG A. Airflow does not detect DAG-level circular dependencies at parse time (only within-DAG task cycles are caught). The pipeline will loop indefinitely, consuming worker slots.

Prevention strategies:
1. **Document DAG dependencies** in a team-maintained dependency map.
2. **Naming conventions**: Distinguish "source" DAGs (never triggered by others) from "sink" DAGs (final consumers).
3. **Use `execution_timeout`** on TriggerDagRunOperator to bound maximum run time.
4. **Unidirectional data flow**: Design pipelines so data always flows in one direction (ingest → transform → serve). No DAG should trigger an "upstream" DAG.

**Q14. What is the worker slot impact of `wait_for_completion=True`?**

When `wait_for_completion=True`, the TriggerDagRunOperator task holds a worker slot for the entire duration of the triggered DAG's run. If your triggered DAG runs for 2 hours, that worker slot is occupied for 2 hours — blocking other tasks.

To avoid this, use `deferrable=True` (Airflow 2.2+):

```python
TriggerDagRunOperator(
    task_id="trigger_and_wait",
    trigger_dag_id="long_running_dag",
    wait_for_completion=True,
    deferrable=True,    # Free the worker slot while waiting
    poke_interval=60,
)
```

With `deferrable=True`, Airflow uses a Triggerer process to poll the status asynchronously, freeing the worker for other work.

**Q15. How does TriggerDagRunOperator work when the Airflow scheduler is in HA (High Availability) mode?**

In HA mode, multiple schedulers run simultaneously. TriggerDagRunOperator writes the triggered DAG run directly to the Airflow metadata database. Any scheduler can then pick up and execute the triggered run. This is safe because:
1. DAG run creation is atomic and idempotent (with `reset_dag_run` handling deduplication).
2. The metadata DB is the single source of truth for all schedulers.
3. With `wait_for_completion=True`, the triggering task polls the DB state — it works regardless of which scheduler manages the triggered run.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Prev operator** | [07_KubernetesPodOperator](../07_KubernetesPodOperator/) |
| **Section root** | [02_Intermediate](../../) |
