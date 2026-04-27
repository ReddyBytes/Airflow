# Project 06 — Event-Driven Asset Pipeline

> **Difficulty:** 🔴 Build Yourself &nbsp;&nbsp; **Level:** Advanced &nbsp;&nbsp; **Est. Time:** 4–6 hours
>
> **Skills you will use:** Asset definitions, `outlets=` on tasks, `schedule=[Asset]`, multi-asset dependencies, asset lineage, Airflow 3 scheduling model

---

## The Situation

You have three pipelines that depend on each other:

- `raw_ingest_dag` fetches orders from an API and lands them in S3
- `transform_dag` cleans the raw data and loads it to the warehouse
- `reporting_dag` runs the daily summary once clean data is available

The old wiring used `ExternalTaskSensor`. The sensor polled every 60 seconds, held a worker slot the entire time, and if the upstream DAG ran even slightly late, the sensor timed out and the downstream DAG failed. You spent more time tuning timeouts than building pipelines.

Airflow 3's **Assets** replace all of that. A task declares what data it produces (`outlets`). A DAG declares what data it needs before it should run (`schedule=[asset]`). Airflow connects the two and fires the downstream DAG the moment the asset is marked updated — no polling, no held slots, no timing assumptions.

Your job: build this three-DAG chain using Assets. Then extend it to a multi-asset pattern where one consumer requires two assets before it fires.

---

## What You Need to Build

```
01_raw_ingest_orders          [schedule: @daily]
  └── ingest_orders
        └── [outlets: raw_orders_asset]
                  |
                  | (triggers automatically)
                  v
02_transform_orders           [schedule: raw_orders_asset]
  └── find_latest_partition
        └── clean_orders
              └── load_to_warehouse
                    └── [outlets: clean_orders_asset]
                                |
                                | (triggers automatically)
                                v
03_daily_order_report         [schedule: clean_orders_asset]
  └── generate_report
        └── write_report_to_s3
              └── [outlets: daily_report_asset]
```

No `TriggerDagRunOperator`. No `ExternalTaskSensor`. Each arrow is an Asset event.

---

## Key Concepts in Play

An **Asset** is a logical URI representing a data resource. The URI is what Airflow tracks — it does not read from or write to the URI itself; it only observes whether a task with `outlets=[that_asset]` succeeded.

```python
from airflow.sdk import Asset

raw_orders_asset   = Asset("s3://my-data-lake/raw/orders/")
clean_orders_asset = Asset("postgres://warehouse/public/orders")
```

**Producing** — attach `outlets=[asset]` to the task that writes the data. When the task succeeds, Airflow marks the asset updated.

**Consuming** — set `schedule=[asset]` on the DAG instead of a cron string. The DAG runs every time all listed assets are updated.

**Multi-asset dependency** — if a DAG lists two assets in its `schedule`, it waits until both are updated from the same logical run before firing. This is the AND condition without any code.

---

## Acceptance Criteria

By the end of this project you must have three DAGs:

1. `01_raw_ingest_orders` — cron-scheduled `@daily`, fetches orders, writes NDJSON to S3, emits `raw_orders_asset`
2. `02_transform_orders` — `schedule=[raw_orders_asset]`, cleans data, loads to Postgres, emits `clean_orders_asset`
3. `03_daily_order_report` — `schedule=[clean_orders_asset]`, aggregates and writes an HTML report to S3, emits `daily_report_asset`

All three share their Asset definitions from a single `pipeline_assets.py` module. No asset URI is duplicated across files.

Then add a 4th DAG that requires two assets simultaneously (use `schedule=[asset_b, asset_c]`). It should only run when both are updated.

---

## Extension Challenges

1. Conditional asset emission — only emit the asset if row count exceeds 10,000 rows; raise a warning and skip otherwise
2. Attach metadata to the asset event so consumers know the row count and partition date without querying the warehouse
3. Trigger the producer for a past date and observe how the consumer chain catches up
4. What happens if the producer fails between emitting asset B and asset C? Write out the answer in a comment block in your DAG

---

⬅️ **Prev:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
