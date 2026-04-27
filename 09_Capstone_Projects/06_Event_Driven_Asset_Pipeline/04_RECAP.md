# Recap — Event-Driven Asset Pipeline

---

## What You Built

A three-DAG system where no DAG polls another and no DAG has a hardcoded dependency on another DAG's ID. A daily ingest DAG fetches orders and emits `raw_orders_asset`. A transform DAG wakes up exactly when that asset is updated, cleans the data, and emits `clean_orders_asset`. A reporting DAG wakes up when clean data is ready and writes the daily summary. The chain fires end-to-end automatically with no human intervention and no timing assumptions.

---

## Skills Demonstrated

**Asset definition and shared module**

All three Asset URIs were defined once in `pipeline_assets.py` and imported into each DAG. This is the only way to guarantee URI consistency. A URI mismatch of even one character breaks the connection silently.

**`outlets=` — producing an asset**

```python
@task(outlets=[raw_orders_asset])
def ingest_orders(ds):
    # write data to S3
    ...
# When this task succeeds, Airflow marks raw_orders_asset as updated.
# No explicit emit call. No return value required for the asset to fire.
```

**`schedule=[asset]` — consuming an asset**

```python
with DAG(
    dag_id="02_transform_orders",
    schedule=[raw_orders_asset],   # ← replaces cron string entirely
    ...
):
```

The DAG has no time-based schedule. It runs once every time `raw_orders_asset` is marked updated — which happens once per successful run of DAG 1, whenever that run completes.

**Multi-asset AND dependency**

```python
schedule=[model_data_asset, validation_asset]
```

Both assets must be updated before the consumer DAG fires. This prevents using yesterday's validation holdout with today's model training data. The AND condition is expressed in one line — no sensor logic, no combining conditions.

**Idempotent load**

Every time the transform DAG runs, it deletes the existing partition and reinserts. This means the entire chain is safe to rerun: trigger DAG 1 for any past date and the correct data flows all the way to the report.

---

## The Mental Model Shift

The key shift from ExternalTaskSensor to Assets:

| Old model | New model |
|---|---|
| Downstream polls: "Is upstream done?" | Upstream announces: "I just produced data X" |
| Worker slot held while polling | Worker slot released immediately |
| Timeout if upstream is late | Consumer fires whenever data arrives |
| Coupling: downstream knows upstream's DAG ID | Decoupling: each DAG only knows Asset URIs |

The Asset model is better when upstream run time is variable. If the API is slow one night and DAG 1 finishes at 4am instead of 2am, the sensor-based DAG 2 has already timed out. The Asset-based DAG 2 simply fires at 4am when the asset is updated.

---

## Common Mistakes Made Here

**Mistake: duplicate Asset URI strings**

If two files define `Asset("s3://my-data-lake/raw/orders/")` and `Asset("s3://my-data-lake/raw/orders")` (no trailing slash), they are different assets. The consumer never triggers. Always import from a single definitions module.

**Mistake: wrong schedule type**

`schedule="@daily"` means run on a cron. `schedule=[my_asset]` means run when the asset fires. If you write `schedule="@daily"` on a consumer DAG, it runs on the cron regardless of whether the producer has finished.

**Mistake: setting `catchup=True` on asset-scheduled DAGs**

Airflow will try to backfill asset-scheduled DAGs, which can trigger unexpected runs. Keep `catchup=False` on all asset-scheduled consumers.

---

## How This Connects to Real Work

Asset-driven scheduling is the Airflow 3 answer to the pipeline fan-out problem. You will see it in:

- Multi-team data platforms (team A produces assets that team B consumes without knowing each other's DAG IDs)
- Data mesh architectures (each domain publishes assets; consumers subscribe)
- ML platforms (training emits a model asset that triggers evaluation, serving, and monitoring DAGs independently)

The lineage graph in the Airflow 3 UI — visible under Assets — is also valuable for data governance: you can see exactly which DAG produced a given data resource and which DAGs depend on it.

---

## What to Try Next

Add metadata to the asset event so consumers know the row count before running:

```python
from airflow.sdk import AssetEventExtra   # Airflow 3 feature

@task(outlets=[raw_orders_asset])
def ingest_orders(ds):
    ...
    return AssetEventExtra(row_count=len(all_orders), partition_date=ds)
```

Then in the consumer DAG, read the metadata from the triggering event context to decide whether to proceed or skip.

---

✅ **Completed:** Asset definitions, `outlets=`, `schedule=[asset]`, multi-asset AND dependency, idempotent loads, decoupled pipeline architecture

🔨 **Practice:** Build a fourth DAG that subscribes to both `clean_orders_asset` and `daily_report_asset` simultaneously; observe it wait for both

➡️ **Next project:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md)

---

⬅️ **Prev:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
