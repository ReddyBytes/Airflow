# Asset-Driven Scheduling — Interview Q&A

## Navigation
⬅️ **Prev: [What's New in Airflow 3](../30_Whats_New_in_Airflow_3/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Versioning](../32_DAG_Versioning/Theory.md)**

---

## Q1: What is an Asset in Airflow 3?

An Asset is a named logical reference to a data artifact — a file, table, API output, or any piece of data. Assets are identified by a URI string (`s3://bucket/path/file.parquet`). Airflow tracks when tasks mark assets as updated, and uses those events to trigger downstream DAGs.

Assets are not the data themselves. They are Airflow's way of representing data dependencies between DAGs. When a task with `outlets=[my_asset]` completes successfully, Airflow records that `my_asset` was updated, and any DAG with `schedule=[my_asset]` gets a new run triggered.

---

## Q2: What is the difference between Assets in Airflow 3 and Datasets in Airflow 2?

They are functionally the same concept — Assets is the renamed and enhanced version of Datasets.

| Feature | Airflow 2 Datasets | Airflow 3 Assets |
|---------|-------------------|-----------------|
| Class name | `Dataset` | `Asset` |
| Import | `from airflow.datasets import Dataset` | `from airflow.sdk import Asset` |
| `@asset` decorator | No | Yes |
| Asset aliases | No | `AssetAlias` |
| OR logic | No | `AssetAny` |
| Complex conditions | No | `AssetAny(AssetAll(...), ...)` |
| Groups | No | `group=` parameter |
| UI lineage | Basic | Full graph |

The URI stays the same, so existing DagRun history is preserved when renaming from `Dataset` to `Asset`.

---

## Q3: How does asset-driven scheduling actually work internally?

When a task with `outlets=[my_asset]` completes:
1. The Worker calls the API Server to record the asset update event
2. The Scheduler polls for asset update events
3. The Scheduler checks which DAGs have `schedule` conditions referencing that asset
4. For each such DAG, the Scheduler checks if all required assets in the condition have been updated since the last DagRun
5. If the condition is satisfied, the Scheduler creates a new DagRun for the consumer DAG

The asset update event is tied to the logical date of the producing DagRun. Consumers receive context about which asset update triggered them.

---

## Q4: What happens with AND logic vs OR logic for multiple assets?

**AND logic** (default): All listed assets must be updated before the consumer DAG runs.

```python
schedule=[asset_a, asset_b]        # AND — both must update
schedule=AssetAll(asset_a, asset_b) # same as above, explicit
```

Airflow tracks which assets have been updated since the last successful DagRun of the consumer. Only when ALL have been updated at least once does it trigger.

**OR logic**: Any one of the listed assets triggers the consumer.

```python
schedule=AssetAny(asset_a, asset_b)  # OR — either triggers a run
```

**Complex**: Combine with nesting.

```python
schedule=AssetAny(AssetAll(asset_a, asset_b), asset_c)
# Triggers when: (a AND b) OR (c alone)
```

---

## Q5: What is the @asset decorator and when should you use it?

The `@asset` decorator is syntactic sugar that creates both an Asset and its producing DAG in one declaration.

```python
@asset(uri="s3://bucket/sales.parquet", schedule="@daily", start_date=...)
def sales_data():
    # write to S3
    pass
```

This creates an `Asset("s3://bucket/sales.parquet")` and a DAG with one task (the decorated function). The function name becomes a reference you can use in consumer DAGs' `schedule=` parameter.

Use `@asset` when the producing task is simple (single function) and you want to co-locate the asset definition with its producing logic. Use the explicit `outlets=[asset]` pattern when your producer DAG has multiple tasks and the asset is produced partway through a complex pipeline.

---

## Q6: How do you reference an asset in a consumer DAG when the asset is defined in a different file?

Define assets in a shared module and import them. The URI is the identity — two `Asset` objects with the same URI refer to the same asset.

```python
# dags/shared/assets.py
from airflow.sdk import Asset
SALES_ASSET = Asset("s3://data/sales.parquet")

# Producer DAG
from shared.assets import SALES_ASSET
@task(outlets=[SALES_ASSET])
def produce(): pass

# Consumer DAG
from shared.assets import SALES_ASSET
with DAG("consumer", schedule=[SALES_ASSET]) as dag: ...
```

Never hardcode the URI string in multiple files — a typo creates a different asset that never gets triggered.

---

## Q7: What is an Asset Alias?

An `AssetAlias` is a stable reference name that can be updated to point to different underlying assets over time. It's useful for "latest version" references.

```python
from airflow.sdk import Asset, AssetAlias

alias = AssetAlias("latest_report")

@task(outlets=[Asset("s3://data/report-2024-03-15.parquet"), alias])
def produce_report():
    pass

# Consumer schedules on the alias — doesn't need to know the versioned URI
with DAG("consume_report", schedule=[alias]) as dag: ...
```

When the producer runs, it updates both the versioned asset and the alias. The consumer triggers because the alias was updated. Next month, the producer might write to a different versioned path, but the alias remains the same.

---

## Q8: Can a DAG have both a cron schedule AND asset-based scheduling?

Yes. You can combine a time-based schedule with asset triggers using `DatasetOrTimeSchedule` (the name may vary by version — check Airflow 3 docs). However, in most cases you want one or the other:

- Use **time-based** schedule for ingestion DAGs that pull from external sources on a cadence
- Use **asset-based** schedule for transformation and reporting DAGs that should react to upstream data

Mixing both means the consumer runs either when the asset is updated OR when the time schedule fires — which can lead to runs with stale data.

---

## Q9: How do you view asset lineage in the Airflow UI?

In Airflow 3's UI:
1. Click **Assets** in the top navigation
2. Select an asset from the list
3. The asset detail page shows:
   - Which DAGs produce it (upstream producers)
   - Which DAGs consume it (downstream consumers)
   - Update history (when it was last updated, by which DagRun)
   - The lineage graph showing the full chain

The lineage graph is particularly useful when you have chains of assets: DAG A → Asset 1 → DAG B → Asset 2 → DAG C. You can see the full dependency chain visually.

---

## Q10: What information is available in a consumer DAG's context about the triggering asset event?

When a consumer DAG runs because an asset was updated, the context contains information about the triggering event:

```python
@task
def process(**context):
    # Get the asset events that triggered this run
    asset_events = context.get("triggering_asset_events", {})

    for asset_uri, events in asset_events.items():
        for event in events:
            print(f"Asset: {asset_uri}")
            print(f"Updated at: {event.timestamp}")
            print(f"Source DAG run: {event.source_dag_id}.{event.source_run_id}")
            print(f"Source task: {event.source_task_id}")
```

This lets you trace exactly which upstream run triggered the current consumer run, useful for auditing and debugging.

---

## Navigation
⬅️ **Prev: [What's New in Airflow 3](../30_Whats_New_in_Airflow_3/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Versioning](../32_DAG_Versioning/Theory.md)**
