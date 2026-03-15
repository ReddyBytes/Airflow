# ExternalTaskSensor — Interview Q&A

---

## Beginner Questions

### Q1: What is ExternalTaskSensor and why would you use it?

**Answer:**

`ExternalTaskSensor` lets one DAG wait for a task (or an entire DAG run) in a **different DAG** to reach a certain state before continuing. It creates a dependency between two separate pipelines without merging them into one.

**Why it matters:** In real data platforms, different teams own different pipelines. A reporting DAG shouldn't run until the ingestion DAG has loaded today's data. But you don't want to merge those two DAGs — they have different owners, different schedules, and different concerns.

`ExternalTaskSensor` is the bridge: it queries the Airflow metadata database for the state of the target task and waits until it sees `"success"`.

```python
from airflow.sensors.external_task import ExternalTaskSensor

wait_for_ingestion = ExternalTaskSensor(
    task_id="wait_for_daily_load",
    external_dag_id="ingestion_pipeline",
    external_task_id="load_complete",
    allowed_states=["success"],
    poke_interval=60,
    timeout=2 * 60 * 60,
    mode="reschedule",
)
```

---

### Q2: What do `external_dag_id` and `external_task_id` do?

**Answer:**

- **`external_dag_id`** (required): the `dag_id` string of the DAG you're waiting for. Must exactly match the `dag_id` defined in that DAG's Python file.
- **`external_task_id`**: the `task_id` of the specific task to wait for within that DAG. If set to `None`, the sensor waits for the **entire DAG run** to complete (all tasks succeed).

```python
# Wait for a specific task
ExternalTaskSensor(
    external_dag_id="data_ingestion",
    external_task_id="validate_and_load",   # Wait for just this task
    ...
)

# Wait for the entire DAG run to succeed
ExternalTaskSensor(
    external_dag_id="data_ingestion",
    external_task_id=None,   # Wait for full DAG completion
    ...
)
```

Waiting for `external_task_id=None` is useful when you don't control the upstream DAG's internals and just need it to be fully done.

---

### Q3: What are `allowed_states` and `failed_states`?

**Answer:**

- **`allowed_states`** (default `["success"]`): the task states that count as "done, proceed." When the sensor finds the target task in one of these states, it returns `True` and succeeds.
- **`failed_states`** (default `None`): if the target task reaches one of these states, the sensor **fails immediately** rather than continuing to wait.

```python
ExternalTaskSensor(
    external_dag_id="upstream_pipeline",
    external_task_id="final_task",
    allowed_states=["success"],
    failed_states=["failed", "upstream_failed"],  # Fail fast if upstream fails
    ...
)
```

**Without `failed_states`:** if the upstream task fails, the sensor will keep poking until its own `timeout` expires — then fail due to timeout. This can mean hours of unnecessary waiting.

**Best practice:** Always set `failed_states=["failed", "upstream_failed"]` so you get fast feedback when the upstream pipeline breaks.

---

### Q4: How does ExternalTaskSensor match execution dates between two DAGs?

**Answer:**

`ExternalTaskSensor` matches task instances by **execution date** in the Airflow metadata database. When your sensor runs, it looks for a task instance in the external DAG with:
- The matching `dag_id`
- The matching `task_id`
- An execution date matching the current run's execution date (or adjusted by `execution_delta`)

**If both DAGs run on the same schedule** (e.g., both daily at midnight), execution dates match automatically — no adjustment needed.

**If they run on different schedules**, the execution dates won't match by default and the sensor will never find anything. This is where `execution_delta` comes in.

---

### Q5: What is `execution_delta` and when do you need it?

**Answer:**

`execution_delta` is a `timedelta` that tells the sensor to look for the external DAG's execution date at a fixed offset from the current DAG's execution date.

**Example:** DAG A runs hourly. DAG B runs daily at midnight. DAG B wants to wait for DAG A's 11pm run (the last run of the previous day). When DAG B's execution date is `2024-01-15 00:00:00`, DAG A's 11pm run has execution date `2024-01-14 23:00:00` — exactly 1 hour earlier.

```python
from datetime import timedelta

ExternalTaskSensor(
    external_dag_id="hourly_dag_a",
    external_task_id="load_complete",
    execution_delta=timedelta(hours=1),
    # Sensor looks for: current_execution_date - timedelta(hours=1)
    # DAG B at 2024-01-15 00:00 → looks for DAG A at 2024-01-14 23:00
    mode="reschedule",
    timeout=3 * 60 * 60,
)
```

Getting `execution_delta` wrong is the most common bug with `ExternalTaskSensor`. When in doubt, check what execution dates exist in the metadata DB for the external DAG.

---

## Intermediate Questions

### Q6: What is `execution_date_fn` and how is it different from `execution_delta`?

**Answer:**

`execution_date_fn` is a function that takes the current DAG's execution date and returns one or more execution dates to look for in the external DAG. It's more powerful than `execution_delta` for complex schedule relationships.

**Use `execution_delta` when:** the offset is always a fixed timedelta (e.g., always 2 hours earlier).

**Use `execution_date_fn` when:** the relationship is dynamic — for example, your daily DAG needs to wait for all 24 hourly runs of today:

```python
from datetime import timedelta

def get_all_hourly_runs(dt):
    """Return execution dates for all 24 hourly runs of the day."""
    return [dt - timedelta(hours=h) for h in range(1, 25)]

ExternalTaskSensor(
    task_id="wait_for_all_hourly_runs",
    external_dag_id="hourly_data_loader",
    external_task_id="load_data",
    execution_date_fn=get_all_hourly_runs,
    allowed_states=["success"],
    mode="reschedule",
    poke_interval=120,
    timeout=4 * 60 * 60,
)
```

The sensor waits until **all** returned execution dates have the target task in an `allowed_state`.

---

### Q7: How does ExternalTaskSensor affect SLA monitoring?

**Answer:**

`ExternalTaskSensor` tasks can delay the entire downstream DAG, which affects SLA calculations. Key points:

1. **SLA is measured from the DAG's execution date, not from task start time.** If your DAG's execution date is midnight but `ExternalTaskSensor` doesn't succeed until 4am (because the upstream DAG ran late), all subsequent tasks start late — and your SLA for tasks after the sensor may be breached.

2. **The sensor itself can breach its SLA.** If you define an SLA on the DAG and the upstream pipeline is consistently late, you'll get SLA miss alerts for the sensor task.

3. **Mitigation strategies:**
   - Set a realistic `timeout` on the sensor that aligns with your SLA
   - Set up alerting on the upstream DAG so you know when it runs late
   - Use `on_sla_miss` callbacks to notify stakeholders

```python
# DAG with SLA monitoring
with DAG(
    dag_id="reporting_pipeline",
    sla_miss_callback=notify_team_on_sla_miss,
    default_args={"sla": timedelta(hours=6)},  # Each task must complete within 6 hrs of execution_date
) as dag:
    wait_for_upstream = ExternalTaskSensor(
        task_id="wait_for_upstream",
        external_dag_id="ingestion_pipeline",
        external_task_id="load_complete",
        timeout=4 * 60 * 60,   # Sensor-specific timeout: give up if upstream never completes
        mode="reschedule",
    )
```

---

### Q8: What are common pitfalls and how do you debug ExternalTaskSensor?

**Answer:**

**Common pitfalls:**

1. **Wrong `execution_delta`** — most common issue. The sensor looks for the wrong execution date and never finds the task. Solution: query the metadata DB to verify what execution dates exist for the external DAG.

2. **Timezone mismatch** — if DAG A uses UTC and DAG B uses a local timezone, execution dates won't align. Ensure both DAGs use the same timezone (`pendulum.timezone("UTC")` recommended).

3. **External DAG has never run** — if the external DAG has no successful runs yet, there's nothing in the DB. The sensor will wait until timeout.

4. **Tasks were manually cleared** — if someone clears the upstream task's state, the sensor may stop finding the "success" state and wait again.

5. **Waiting for `external_task_id=None` but some tasks were skipped** — if the upstream DAG has skipped tasks, the overall DAG run might not be in "success" state.

**Debugging steps:**
```python
# Check what execution dates exist for the external DAG in the metadata DB
SELECT execution_date, state
FROM task_instance
WHERE dag_id = 'your_external_dag'
  AND task_id = 'your_external_task'
ORDER BY execution_date DESC
LIMIT 10;
```

Also check the sensor's task logs — each poke logs the execution date it's looking for and the current state found.

---

### Q9: Can ExternalTaskSensor wait for multiple tasks or multiple DAGs at once?

**Answer:**

`ExternalTaskSensor` natively waits for a **single** task in a **single** external DAG per sensor instance. To wait for multiple, use multiple sensors in parallel:

```python
# Wait for two separate upstream DAGs
wait_for_sales_dag = ExternalTaskSensor(
    task_id="wait_for_sales_pipeline",
    external_dag_id="sales_ingestion",
    external_task_id=None,  # full DAG completion
    mode="reschedule", poke_interval=60, timeout=7200,
)

wait_for_marketing_dag = ExternalTaskSensor(
    task_id="wait_for_marketing_pipeline",
    external_dag_id="marketing_ingestion",
    external_task_id=None,
    mode="reschedule", poke_interval=60, timeout=7200,
)

run_report = PythonOperator(task_id="run_combined_report", ...)

# Both sensors run in parallel, report starts only when both succeed
[wait_for_sales_dag, wait_for_marketing_dag] >> run_report
```

For waiting on **multiple tasks within the same DAG**, you can use `external_task_ids` (list, available in newer provider versions) or chain multiple sensors.

---

## Advanced Questions

### Q10: What is the difference between ExternalTaskSensor and Airflow Datasets (Data-Aware Scheduling)?

**Answer:**

Both create cross-DAG dependencies, but they work very differently:

| Aspect | `ExternalTaskSensor` | Datasets (Airflow 2.4+) |
|---|---|---|
| Dependency type | Task-to-task (execution date match) | Data-to-DAG trigger |
| Scheduling | Downstream DAG runs on its own schedule | Downstream DAG triggered **when dataset is updated** |
| Configuration | Add sensor task to downstream DAG | Declare `outlets` (producer) and `schedule` (consumer) |
| Execution date | Requires matching / delta logic | New logical date per trigger |
| Cross-schedule | Works with `execution_delta` | Handles mismatched schedules naturally |
| Best for | Time-based DAG coordination | Event-driven data pipeline triggers |

```python
# Datasets approach (Airflow 2.4+ / 3.x) — alternative to ExternalTaskSensor
from airflow import Dataset

orders_dataset = Dataset("s3://my-bucket/orders/{{ ds }}/")

# Producer DAG declares what it produces
with DAG(...) as producer_dag:
    load_task = PythonOperator(
        task_id="load_orders",
        python_callable=load_orders,
        outlets=[orders_dataset],   # This DAG "produces" the dataset
    )

# Consumer DAG runs when the dataset is updated — no sensor needed
with DAG(schedule=[orders_dataset], ...) as consumer_dag:
    ...
```

For new Airflow 3 pipelines, consider Datasets for event-driven triggers. Use `ExternalTaskSensor` when you need fine-grained control over execution date alignment or when the upstream DAG cannot be modified to declare Dataset outlets.

---

### Q11: How do you handle the case where the upstream DAG was manually triggered (not scheduled)?

**Answer:**

Manually triggered DAGs get an execution date equal to the time they were triggered (not a scheduled interval). This means `ExternalTaskSensor` with `execution_delta` won't find them by a fixed offset.

**Solutions:**

1. **Use `execution_date_fn` with a database query** — look for the most recent successful run regardless of exact execution date:

```python
def get_latest_successful_run(dt):
    """Find the most recent execution date for the upstream DAG."""
    from airflow.models import DagRun
    from airflow.utils.state import DagRunState

    runs = (
        DagRun.find(dag_id="upstream_dag", state=DagRunState.SUCCESS)
    )
    if runs:
        return [max(r.execution_date for r in runs)]
    return [dt]  # Fallback to current — sensor will wait until something exists

ExternalTaskSensor(
    external_dag_id="upstream_dag",
    external_task_id=None,
    execution_date_fn=get_latest_successful_run,
    mode="reschedule",
    timeout=3600,
)
```

2. **Use Datasets instead** — dataset-aware scheduling triggers the downstream DAG when the upstream DAG actually updates the dataset, regardless of execution date alignment.

3. **Establish a convention** — require that manually triggered upstream DAGs use a fixed execution date (e.g., today's midnight) to maintain predictable alignment.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [HttpSensor](../02_HttpSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [S3KeySensor](../04_S3KeySensor/Theory.md)
