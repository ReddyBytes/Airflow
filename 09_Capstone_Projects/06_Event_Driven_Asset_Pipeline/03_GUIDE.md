# Guide — Event-Driven Asset Pipeline

> **Difficulty: 🔴 Build Yourself.** This guide explains the concepts and acceptance criteria. It does not give you step-by-step code. Consult `02_ARCHITECTURE.md` for the design. Open `src/solution.py` only after a genuine attempt.

---

## Before You Start

Read `01_MISSION.md` and `02_ARCHITECTURE.md` fully. The architecture section contains the complete ASCII graph of all three DAGs and their asset connections. Your implementation should match that graph exactly.

Make sure you can import `Asset` from `airflow.sdk`:

```python
from airflow.sdk import Asset
```

If this fails, you are on Airflow 2 — upgrade to Airflow 3 before proceeding.

---

## The Core Rule

Before writing any DAG code, create a shared asset definitions file:

```python
# dags/pipeline_assets.py
from airflow.sdk import Asset

raw_orders_asset    = Asset("s3://my-data-lake/raw/orders/")
clean_orders_asset  = Asset("postgres://warehouse/public/orders")
daily_report_asset  = Asset("s3://my-reports/daily/orders/")
```

Every DAG imports from this file. A URI mismatch of even one character breaks the connection silently — the trigger never fires and there is no error message.

---

## What to Build: Three DAGs

**DAG 1 — `01_raw_ingest_orders`**

- Schedule: `@daily` (cron-based — this is the pipeline's entry point)
- Tasks: fetch orders from an HTTP API with pagination, write as NDJSON to S3, verify the file exists
- Asset produced: `raw_orders_asset` via `outlets=[raw_orders_asset]` on the write task
- The `ingest_orders` task should handle multiple pages (loop until `has_next_page` is false)

**DAG 2 — `02_transform_orders`**

- Schedule: `schedule=[raw_orders_asset]` — no cron
- Tasks: find the latest S3 partition, read NDJSON, clean (drop nulls on key columns, filter negative amounts, normalise dates), load to Postgres, confirm row count
- Asset consumed: `raw_orders_asset` — what triggers this DAG
- Asset produced: `clean_orders_asset` — emitted by the `load_to_warehouse` task
- The load must be idempotent: DELETE existing rows for the partition date, then INSERT

**DAG 3 — `03_daily_order_report`**

- Schedule: `schedule=[clean_orders_asset]` — no cron
- Tasks: query the warehouse for a daily summary (total orders, revenue, unique customers, cancellations), write an HTML report to S3
- Asset consumed: `clean_orders_asset`
- Asset produced: `daily_report_asset`

---

## Multi-Asset AND Dependency (Extension)

Once the three-DAG chain is working, add a fourth DAG that only fires when two assets arrive together:

```python
with DAG(
    dag_id="04_combined_analysis",
    schedule=[asset_a, asset_b],  # both must be updated before this fires
    ...
):
    ...
```

Define two new assets (`model_data_asset` and `validation_asset`), have a producer task emit both in the same run, and verify that your consumer DAG waits for both before triggering.

---

## Hints (Only Read If Stuck)

**Hint 1 — How does `outlets` work with the `@task` decorator?**

```python
@task(outlets=[my_asset])
def my_producer_task():
    # do work
    return result
# When this task succeeds, Airflow marks my_asset as updated.
# No explicit emit call is needed.
```

**Hint 2 — How does the consumer DAG know which run triggered it?**

When an asset triggers a DAG run, the `data_interval_start` context variable holds the logical date of the producer run that emitted the asset. Use this to find the correct partition:

```python
@task
def find_latest_partition(data_interval_start=None, **context):
    ds = data_interval_start.strftime("%Y-%m-%d") if data_interval_start else context["ds"]
    ...
```

**Hint 3 — Idempotent load pattern**

```python
hook.run("DELETE FROM warehouse.orders WHERE order_date = %s", parameters=[order_date])
hook.insert_rows(table="warehouse.orders", rows=rows, target_fields=columns, commit_every=500)
```

**Hint 4 — Verifying the chain**

```bash
airflow dags trigger 01_raw_ingest_orders
# Then watch in the UI: Assets page shows raw_orders_asset last updated timestamp change
# DAG 2 appears in the queue automatically
# DAG 3 appears after DAG 2 finishes
```

---

## Acceptance Criteria

Before you consider this project complete:

- [ ] `pipeline_assets.py` exists; all three DAGs import from it
- [ ] DAG 1 produces `raw_orders_asset`; DAG 2 consumes it
- [ ] DAG 2 produces `clean_orders_asset`; DAG 3 consumes it
- [ ] DAG 3 produces `daily_report_asset`
- [ ] No DAG uses a time-based schedule except DAG 1
- [ ] Load task in DAG 2 is idempotent (safe to rerun for the same date)
- [ ] Airflow Assets UI shows the lineage graph connecting all three DAGs
- [ ] Fourth DAG (`schedule=[asset_a, asset_b]`) fires only when both assets are updated

---

⬅️ **Prev:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
