# Event-Driven Asset Pipeline — Step by Step

In Airflow 3, **Assets** (formerly Datasets) let DAGs communicate with each other
without polling or complex cross-DAG dependencies. When a producer DAG writes to an
Asset, Airflow automatically triggers any DAGs that subscribe to that Asset.

This project builds a three-DAG chain:
1. **Raw ingestion DAG** — lands data and produces `raw_orders` Asset
2. **Transform DAG** — triggered by `raw_orders`, produces `clean_orders` Asset
3. **Reporting DAG** — triggered by `clean_orders`, generates the daily report

---

## What You Will Build

```
[Schedule: @daily]                  [Triggered by Asset]          [Triggered by Asset]
raw_ingest_dag                  →   transform_dag             →   reporting_dag
  └── ingest_from_api               └── clean_and_enrich           └── generate_report
      └── write_to_s3                   └── load_to_warehouse           └── send_email
          └── [produces raw_orders]         └── [produces clean_orders]
```

No cross-DAG dependencies in code. Each DAG is completely independent — they are
connected only through Asset declarations.

---

## Prerequisites

```bash
pip install apache-airflow \
            apache-airflow-providers-amazon \
            apache-airflow-providers-postgres \
            pandas requests
```

---

## Step 1 — Understand Airflow 3 Assets

An Asset is a logical URI that represents a data resource:

```python
from airflow.sdk import Asset

raw_orders_asset  = Asset("s3://my-bucket/raw/orders/")
clean_orders_asset = Asset("postgres://warehouse/orders")
```

- **Producing** an Asset: add it to a task's `outlets` parameter.
  When that task completes successfully, Airflow marks the Asset as updated.
- **Consuming** an Asset: add it to a DAG's `schedule` parameter.
  The DAG runs automatically whenever all its input Assets are updated.

---

## Step 2 — Define the Assets

Create a shared module so all three DAGs reference the same Asset objects:

```python
# dags/assets.py
from airflow.sdk import Asset

raw_orders_asset    = Asset("s3://my-data-lake/raw/orders/")
clean_orders_asset  = Asset("postgres://warehouse/public/orders")
report_asset        = Asset("s3://my-reports/daily/orders/")
```

Import from this module in each DAG:
```python
from assets import raw_orders_asset, clean_orders_asset, report_asset
```

---

## Step 3 — Build the Raw Ingestion DAG

```python
# dags/01_raw_ingest_dag.py
from datetime import datetime
from airflow.sdk import DAG, Asset, task
import requests, json

raw_orders_asset = Asset("s3://my-data-lake/raw/orders/")

@task(outlets=[raw_orders_asset])
def ingest_orders_from_api(ds: str = None) -> dict:
    """
    Fetch orders from the REST API and write to S3.
    The `outlets=[raw_orders_asset]` declaration tells Airflow:
    'when this task succeeds, mark raw_orders_asset as updated'.
    """
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    # Fetch from API
    resp = requests.get(
        f"https://api.orders.company.com/orders?date={ds}",
        headers={"Authorization": "Bearer {{ var.value.api_token }}"},
        timeout=30,
    )
    resp.raise_for_status()
    orders = resp.json()["data"]

    # Write to S3 as NDJSON
    s3 = S3Hook(aws_conn_id="aws_default")
    key = f"raw/orders/{ds}/orders.ndjson"
    content = "\n".join(json.dumps(row) for row in orders)
    s3.load_string(content, key=key, bucket_name="my-data-lake", replace=True)

    print(f"Ingested {len(orders)} orders for {ds} → s3://my-data-lake/{key}")
    return {"s3_key": key, "row_count": len(orders)}


with DAG(
    dag_id="01_raw_ingest_orders",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",              # triggered by time schedule
    catchup=False,
    tags=["event-driven", "producer"],
) as dag:
    ingest_orders_from_api()
```

---

## Step 4 — Build the Transform DAG

```python
# dags/02_transform_dag.py
from datetime import datetime
from airflow.sdk import DAG, Asset, task
import json, pandas as pd

raw_orders_asset   = Asset("s3://my-data-lake/raw/orders/")
clean_orders_asset = Asset("postgres://warehouse/public/orders")

@task
def find_latest_raw_file() -> str:
    """Find the most recently updated raw orders file."""
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    hook = S3Hook(aws_conn_id="aws_default")
    keys = hook.list_keys(bucket_name="my-data-lake", prefix="raw/orders/")
    latest = sorted(keys)[-1]                   # lexicographic sort works with ISO dates
    print(f"Latest raw file: {latest}")
    return latest

@task(outlets=[clean_orders_asset])
def clean_and_load(s3_key: str) -> dict:
    """Read raw NDJSON, clean, and insert into warehouse."""
    import io
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    # Read from S3
    s3 = S3Hook(aws_conn_id="aws_default")
    content = s3.read_key(s3_key, bucket_name="my-data-lake")
    rows = [json.loads(line) for line in content.strip().split("\n")]
    df = pd.DataFrame(rows)

    # Clean
    df = df.dropna(subset=["order_id", "customer_id"])
    df = df[df["amount"] >= 0]
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.date
    df["loaded_at"] = pd.Timestamp.utcnow()

    # Load to warehouse
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")
    hook.run("DELETE FROM warehouse.orders WHERE order_date = %s",
             parameters=[df["order_date"].iloc[0]])

    hook.insert_rows(
        table="warehouse.orders",
        rows=[tuple(r) for r in df.itertuples(index=False)],
        target_fields=list(df.columns),
        commit_every=500,
    )

    print(f"Loaded {len(df)} clean rows to warehouse.orders")
    return {"warehouse_rows": len(df)}


with DAG(
    dag_id="02_transform_orders",
    start_date=datetime(2024, 1, 1),
    schedule=[raw_orders_asset],    # TRIGGERED BY ASSET — not a time schedule
    catchup=False,
    tags=["event-driven", "consumer", "producer"],
) as dag:
    latest = find_latest_raw_file()
    clean_and_load(s3_key=latest)
```

---

## Step 5 — Build the Reporting DAG

```python
# dags/03_reporting_dag.py
from datetime import datetime
from airflow.sdk import DAG, Asset, task
from airflow.operators.email import EmailOperator

clean_orders_asset = Asset("postgres://warehouse/public/orders")

@task
def generate_daily_report() -> dict:
    """Aggregate warehouse orders into a summary report."""
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")
    summary = hook.get_pandas_df("""
        SELECT
            order_date,
            COUNT(*)              AS total_orders,
            SUM(amount)           AS revenue,
            AVG(amount)           AS avg_order_value,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM warehouse.orders
        WHERE order_date = CURRENT_DATE - 1
        GROUP BY order_date
    """)
    print(summary.to_string(index=False))
    return summary.to_dict(orient="records")[0]

with DAG(
    dag_id="03_daily_order_report",
    start_date=datetime(2024, 1, 1),
    schedule=[clean_orders_asset],  # TRIGGERED BY ASSET
    catchup=False,
    tags=["event-driven", "consumer", "reporting"],
) as dag:
    report_data = generate_daily_report()
```

---

## Step 6 — Observe the Chain in Action

```bash
# Manually trigger the first DAG
airflow dags trigger 01_raw_ingest_orders

# Watch in the UI:
# 1. 01_raw_ingest_orders completes → raw_orders_asset marked as updated
# 2. Airflow automatically queues 02_transform_orders
# 3. 02_transform_orders completes → clean_orders_asset marked as updated
# 4. Airflow automatically queues 03_daily_order_report
```

In the Airflow 3 UI, navigate to **Assets** to see:
- Each Asset's last updated timestamp
- Which DAGs produce and consume it
- The full lineage graph

---

## Step 7 — Multi-Hop Asset Chain Diagram

```
01_raw_ingest_orders
  └─ ingest_orders_from_api
       └─ [outlets: raw_orders_asset]
              ↓ (triggers automatically)
02_transform_orders
  └─ find_latest_raw_file → clean_and_load
                              └─ [outlets: clean_orders_asset]
                                        ↓ (triggers automatically)
                             03_daily_order_report
                               └─ generate_daily_report
```

Each arrow is an Asset dependency — no `TriggerDagRunOperator`, no `ExternalTaskSensor`.

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Full Code** | [Code_Example.md](./Code_Example.md) |
| **Parent: Advanced Projects** | [03_Advanced_Projects](../Readme.md) |
| **Previous: ML Training Pipeline** | [05_ML_Training_Pipeline](../05_ML_Training_Pipeline/Project_Guide.md) |
| **All Projects** | [08_Projects](../../Readme.md) |
