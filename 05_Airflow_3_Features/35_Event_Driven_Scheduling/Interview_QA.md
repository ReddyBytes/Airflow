# Event-Driven Scheduling — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Object Storage](../36_Object_Storage/Theory.md)**

---

## Q1: What is event-driven scheduling in Airflow 3?

Event-driven scheduling means that **a DAG run is triggered by a data event rather than a clock**. In Airflow 3, the event mechanism is the **Asset**. When a task marks an asset as updated (by completing successfully with `outlets=[my_asset]`), the Scheduler evaluates whether any DAGs scheduled on that asset should now run.

Before Airflow 2.4, every DAG needed a cron/timetable schedule. If you wanted DAG B to run after DAG A produced some data, you had to use an `ExternalTaskSensor` or poll for the data. Both approaches waste resources and add latency.

Event-driven scheduling replaces that pattern: DAG B simply declares `schedule=[my_asset]` and Airflow handles the rest.

---

## Q2: How exactly does Airflow know when to trigger an asset-scheduled DAG?

The mechanism step by step:

1. A task with `outlets=[my_asset]` completes successfully
2. The Worker makes an HTTP call to the API Server: "asset `s3://bucket/file` was just updated by run X, task Y"
3. The API Server writes an **asset event record** to the `asset_event` table in the metadata database
4. The Scheduler's main loop periodically queries the `asset_event` table
5. For each pending event, the Scheduler checks: "which consumer DAGs have a schedule condition referencing this asset?"
6. For each consumer DAG, it checks: "have all assets in this DAG's schedule condition been updated since the last successful run of this consumer?"
7. If the condition is fully satisfied: the Scheduler creates a new `DagRun` for the consumer

The key term is **"since the last successful run"**. Airflow tracks which events have been consumed by each consumer DAG. An asset update is consumed once it triggers a run; the counter resets for that DAG.

---

## Q3: How does event-driven scheduling differ from time-based scheduling?

| | Time-Based | Event-Driven |
|--|-----------|-------------|
| **Trigger** | Clock (cron, @daily, etc.) | Asset update event |
| **Run frequency** | Fixed cadence | Whenever upstream data arrives |
| **Handles late data?** | No — runs regardless of whether data is ready | Yes — waits until the data event fires |
| **Idle runs** | Possible (runs even if upstream data is stale) | Never — runs only when data changed |
| **Scheduling class** | `CronTriggerTimetable`, `DeltaTriggerTimetable` | Asset condition |
| **Typical use** | Ingestion from external APIs with fixed schedules | Transformation and reporting DAGs |

Rule of thumb: use **time-based** for the first layer of your pipeline (pulling from sources on a cadence), and **event-driven** for all downstream transformation and reporting layers.

---

## Q4: What is the difference between `schedule=[asset_a, asset_b]` and `schedule=AssetAny(asset_a, asset_b)`?

`schedule=[asset_a, asset_b]` is **AND logic**. The DAG runs only after both `asset_a` AND `asset_b` have been updated since the last run. It is equivalent to `schedule=AssetAll(asset_a, asset_b)`.

`schedule=AssetAny(asset_a, asset_b)` is **OR logic**. The DAG runs when either `asset_a` OR `asset_b` is updated. Each update to either asset triggers a run.

Practical example:
```python
# AND — build a combined report only when BOTH sources are fresh
schedule=[DAILY_SALES, DAILY_RETURNS]

# OR — send an alert as soon as EITHER anomaly source detects a problem
schedule=AssetAny(FRAUD_SIGNAL, LATENCY_SIGNAL)
```

You can also nest them:
```python
# (A AND B) OR C
schedule=AssetAny(AssetAll(asset_a, asset_b), asset_c)
```

---

## Q5: How does Airflow handle the case where an asset is updated multiple times before the consumer runs?

Airflow does **not queue up one run per update**. It queues at most one pending run per consumer DAG.

Scenario: `asset_a` is updated 3 times in quick succession, but your consumer DAG takes 20 minutes to run.

- First update: consumer gets queued/triggered
- Second update: consumer is already running or queued — a new pending trigger is noted
- Third update: same — updates the "pending trigger" but does not create a second run

When the first consumer run finishes, Airflow may trigger one more run if asset events are still unprocessed. But it does not create 3 queued runs. This is intentional: you almost always want "process the latest data" not "process each intermediate state."

If you need to process every individual event, use a traditional queue (Kafka, SQS) consumed inside the task, not Airflow's asset mechanism.

---

## Q6: Can you combine an asset schedule with a cron timetable?

Yes. Use `AssetOrTimeSchedule`:

```python
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

with DAG(
    dag_id="report_with_fallback",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 8 * * *", timezone="UTC"),
        assets=[DAILY_SALES],
    ),
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

This DAG runs when `DAILY_SALES` is updated OR at 08:00 UTC daily — whichever comes first.

**Use case:** A morning report that should run as soon as the overnight data load completes, but must also run at 08:00 with whatever data is available, even if the overnight load is still running.

---

## Q7: What are real-world use cases for event-driven scheduling?

**1. ETL pipeline chain:**
Ingestion DAG writes raw data → marks `raw_orders` asset → Transform DAG picks it up → marks `clean_orders` asset → Reporting DAG builds the dashboard.

**2. ML model retraining:**
Feature engineering DAG produces `training_features` asset → Model training DAG is triggered automatically → Model evaluation produces `model_quality_metrics` asset → Deployment DAG triggers if metrics pass threshold.

**3. Cross-team data contracts:**
Team A owns the `sales` asset. Team B's DAGs schedule on it. When Team A's pipeline runs (on whatever schedule), Team B's pipelines automatically run downstream. No coordination required.

**4. Multi-region data sync:**
A DAG in Region A writes to S3 and marks an asset. A consumer DAG in Region B is triggered to pull the data and replicate it locally.

**5. Data quality gates:**
A validation DAG marks a `validated_data` asset only if quality checks pass. Downstream DAGs schedule on `validated_data` — they never process bad data because the asset is never marked on failure.

---

## Q8: How do you debug why an asset-triggered DAG is not running?

Work through this checklist in order:

**1. Did the producer task actually succeed?**
```bash
airflow tasks states-for-dag-run producer_dag latest_run_id
# Look for "success" state on the task with outlets=[]
```

**2. Is the asset event recorded?**
```bash
# Check asset event history in the UI: Assets > select asset > Events tab
# Or via CLI:
airflow assets events list --asset-uri "s3://bucket/file.parquet"
```

**3. Are the URIs identical?**
If the producer uses `Asset("s3://bucket/file.parquet")` and the consumer uses `Asset("s3://bucket/file.parquet/")` (note trailing slash), they are different assets. Both URIs must be character-for-character identical.

**4. Is the consumer DAG active?**
A paused DAG will not be triggered even if the asset event fires. Unpause it:
```bash
airflow dags unpause consumer_dag
```

**5. Has the consumer ever run successfully before?**
The first time you deploy a consumer, Airflow may not trigger it immediately — it needs a baseline "last successful run" timestamp to compare against. Trigger the first run manually.

---

## Q9: How does event-driven scheduling interact with `catchup=True`?

Asset-scheduled DAGs behave differently from time-scheduled DAGs with `catchup=True`.

Time-scheduled DAGs with `catchup=True` create one run per missed interval between `start_date` and now.

Asset-scheduled DAGs **do not have intervals**. They have no concept of "missed" runs. Airflow will not create historical runs just because the asset was updated many times in the past. It only triggers new runs from the moment the DAG is activated going forward.

If you need to backfill an asset-scheduled DAG, trigger runs manually:
```bash
airflow dags trigger consumer_dag --logical-date 2026-01-01T00:00:00
```

---

## Q10: What context information is available to a task in an asset-triggered DAG run?

When an asset event triggers a DAG run, the tasks in that run have access to information about the triggering event via the task context:

```python
@task
def process_triggered_data(**context):
    # Dict of {asset_uri: [list of AssetEvent objects]}
    asset_events = context.get("triggering_asset_events", {})

    for asset_uri, events in asset_events.items():
        print(f"Asset that triggered this run: {asset_uri}")
        for event in events:
            print(f"  Updated at:       {event.timestamp}")
            print(f"  Producer DAG:     {event.source_dag_id}")
            print(f"  Producer run ID:  {event.source_run_id}")
            print(f"  Producer task:    {event.source_task_id}")
            # Use extra metadata set by the producer task, if any
            print(f"  Extra:            {event.extra}")
```

This lets you implement conditional logic inside the consumer: "if the upstream DAG that triggered us is the emergency reload, skip validation and go straight to publishing."

---

## Q11: Can a task pass extra metadata alongside an asset update event?

Yes. You can attach a dictionary of extra metadata to an asset update using the `AssetEvent` context inside the producing task:

```python
from airflow.decorators import task
from airflow.sdk import Asset

SALES_ASSET = Asset("s3://data/sales.parquet")

@task(outlets=[SALES_ASSET])
def upload_sales(*, outlet_events):
    # Write the file...
    rows_written = 150_000

    # Attach metadata to the asset event
    outlet_events[SALES_ASSET].extra = {
        "row_count":  rows_written,
        "source":     "oracle_erp",
        "loaded_by":  "ingest_sales_dag",
    }
```

The consumer can then read `event.extra` to make decisions or for logging/auditing.

---

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Object Storage](../36_Object_Storage/Theory.md)**
