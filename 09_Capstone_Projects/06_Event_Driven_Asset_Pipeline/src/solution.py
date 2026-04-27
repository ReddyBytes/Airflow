"""
event_driven_pipeline_solution.py
==================================
Three complete Airflow 3 DAGs connected through Assets.

DAG 1: 01_raw_ingest_orders    — cron @daily, fetches orders, produces raw_orders_asset
DAG 2: 02_transform_orders     — triggered by raw_orders_asset, produces clean_orders_asset
DAG 3: 03_daily_order_report   — triggered by clean_orders_asset, produces daily_report_asset

No ExternalTaskSensor. No TriggerDagRunOperator.
Each arrow in the chain is an Asset dependency.

Required Airflow connections:
  - aws_default          : S3 access
  - postgres_warehouse   : Postgres warehouse
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import requests

from airflow.sdk import DAG, Asset, task
from airflow.operators.email import EmailOperator


# ─────────────────────────────────────────────────────────────────────────────
# Shared asset definitions
# In a real project these live in dags/pipeline_assets.py and are imported.
# Defined inline here so this file is self-contained.
# ─────────────────────────────────────────────────────────────────────────────

raw_orders_asset = Asset(
    uri="s3://my-data-lake/raw/orders/",
    extra={"description": "Raw orders landed from API", "format": "ndjson"},
)
clean_orders_asset = Asset(
    uri="postgres://warehouse/public/orders",
    extra={"description": "Validated and cleaned orders in Postgres warehouse"},
)
daily_report_asset = Asset(
    uri="s3://my-reports/daily/orders/",
    extra={"description": "Daily order summary report (HTML)"},
)


# ─────────────────────────────────────────────────────────────────────────────
# DAG 1 — Raw Ingest (Producer)
# ─────────────────────────────────────────────────────────────────────────────

@task(
    outlets=[raw_orders_asset],     # ← marks asset updated when task succeeds
    retries=3,
    retry_delay=timedelta(minutes=2),
    doc_md="Fetch daily orders from REST API and write to S3 as NDJSON.",
)
def ingest_orders(ds: str | None = None) -> dict:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    # Paginated API fetch
    base_url   = "https://api.orders.company.com/orders"
    all_orders = []
    page       = 1

    while True:
        resp = requests.get(
            base_url,
            params={"date": ds, "page": page, "page_size": 500},
            headers={"Authorization": "Bearer {{ var.value.orders_api_token }}"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        batch   = payload.get("data", [])
        all_orders.extend(batch)

        if not payload.get("has_next_page", False):
            break
        page += 1

    print(f"[ingest] Fetched {len(all_orders)} orders for {ds} across {page} pages")

    # Write NDJSON to S3
    s3            = S3Hook(aws_conn_id="aws_default")
    key           = f"raw/orders/{ds}/orders.ndjson"
    ndjson_content = "\n".join(json.dumps(row) for row in all_orders)

    s3.load_string(
        string_data=ndjson_content,
        key=key,
        bucket_name="my-data-lake",
        replace=True,               # ← idempotent: overwrite if key exists
    )
    print(f"[ingest] Written to s3://my-data-lake/{key}")
    return {"s3_key": key, "row_count": len(all_orders), "date": ds}


@task(doc_md="Verify S3 key exists after write. Raises if missing.")
def verify_ingest(ingest_result: dict) -> None:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    hook   = S3Hook(aws_conn_id="aws_default")
    exists = hook.check_for_key(ingest_result["s3_key"], bucket_name="my-data-lake")

    if not exists:
        raise FileNotFoundError(
            f"S3 key not found after write: {ingest_result['s3_key']}"
        )
    print(
        f"[verify] Confirmed. {ingest_result['row_count']} rows for {ingest_result['date']}"
    )


with DAG(
    dag_id="01_raw_ingest_orders",
    description="Fetch orders from API → write to S3. Produces raw_orders_asset.",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",             # ← only this DAG uses a cron schedule
    catchup=False,
    default_args={"owner": "data-engineering"},
    tags=["event-driven", "producer", "ingest"],
) as dag_ingest:
    ingested = ingest_orders()
    verify_ingest(ingest_result=ingested)


# ─────────────────────────────────────────────────────────────────────────────
# DAG 2 — Transform Orders (Consumer + Producer)
# ─────────────────────────────────────────────────────────────────────────────

@task(doc_md="Identify the most recently modified S3 prefix to process.")
def find_latest_partition() -> str:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    hook    = S3Hook(aws_conn_id="aws_default")
    prefixes = hook.list_prefixes(
        bucket_name="my-data-lake",
        prefix="raw/orders/",
        delimiter="/",
    )
    # prefixes: ["raw/orders/2024-01-14/", "raw/orders/2024-01-15/", ...]
    latest_prefix = sorted(prefixes)[-1]  # ← lexicographic sort works with ISO dates
    key = f"{latest_prefix}orders.ndjson"
    print(f"[find_partition] Latest key: {key}")
    return key


@task(doc_md="Read NDJSON, clean rows, return as JSON records string.")
def clean_orders(s3_key: str) -> str:
    import io
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    hook    = S3Hook(aws_conn_id="aws_default")
    content = hook.read_key(s3_key, bucket_name="my-data-lake")
    rows    = [json.loads(line) for line in content.strip().split("\n") if line.strip()]
    df      = pd.DataFrame(rows)

    original_count = len(df)

    # Cleaning rules — applied in order
    df = df.dropna(subset=["order_id", "customer_id"])
    df = df[df["amount"].astype(float) >= 0.01]
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["order_date"])        # drop rows where date parse failed
    df["currency"] = df["currency"].str.upper().str.strip()
    df["amount"]   = df["amount"].astype(float).round(2)

    print(
        f"[clean] {original_count} rows in → {len(df)} rows out "
        f"({original_count - len(df)} dropped)"
    )
    return df.to_json(orient="records")


@task(
    outlets=[clean_orders_asset],   # ← emits asset when load succeeds
    doc_md="Load cleaned DataFrame into warehouse.orders. Idempotent via DELETE+INSERT.",
)
def load_to_warehouse(clean_json: str) -> dict:
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    df = pd.DataFrame(json.loads(clean_json))
    if df.empty:
        raise ValueError("No rows to load after cleaning — check upstream data quality")

    hook       = PostgresHook(postgres_conn_id="postgres_warehouse")
    order_date = df["order_date"].iloc[0]

    # Idempotent: delete partition first, then insert
    hook.run(
        "DELETE FROM warehouse.orders WHERE order_date = %s",
        parameters=[order_date],
    )
    hook.insert_rows(
        table="warehouse.orders",
        rows=[tuple(r) for r in df.itertuples(index=False)],
        target_fields=list(df.columns),
        commit_every=500,
    )

    # Confirm
    count = hook.get_first(
        "SELECT COUNT(*) FROM warehouse.orders WHERE order_date = %s",
        parameters=[order_date],
    )[0]
    print(f"[load] warehouse.orders has {count} rows for {order_date}")
    return {"date": order_date, "warehouse_rows": count}


with DAG(
    dag_id="02_transform_orders",
    description="Triggered by raw_orders_asset → clean → load → produces clean_orders_asset",
    start_date=datetime(2024, 1, 1),
    schedule=[raw_orders_asset],    # ← Asset-based schedule: no cron
    catchup=False,
    default_args={"owner": "data-engineering", "retries": 2},
    tags=["event-driven", "consumer", "producer", "transform"],
) as dag_transform:
    s3_key  = find_latest_partition()
    cleaned = clean_orders(s3_key=s3_key)
    load_to_warehouse(clean_json=cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# DAG 3 — Daily Order Report (Consumer)
# ─────────────────────────────────────────────────────────────────────────────

@task(doc_md="Aggregate warehouse orders into a daily summary.")
def generate_report() -> dict:
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    hook    = PostgresHook(postgres_conn_id="postgres_warehouse")
    summary = hook.get_pandas_df("""
        SELECT
            order_date,
            COUNT(*)                                          AS total_orders,
            ROUND(SUM(amount)::numeric, 2)                    AS total_revenue,
            ROUND(AVG(amount)::numeric, 2)                    AS avg_order_value,
            COUNT(DISTINCT customer_id)                       AS unique_customers,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancellations
        FROM warehouse.orders
        WHERE order_date = (SELECT MAX(order_date) FROM warehouse.orders)
        GROUP BY order_date
    """)

    if summary.empty:
        raise ValueError("No data found in warehouse.orders for latest date")

    row = summary.iloc[0].to_dict()
    print(f"[report] Summary: {row}")
    return row


@task(
    outlets=[daily_report_asset],   # ← emits asset when report is written
    doc_md="Write the daily HTML report to S3.",
)
def write_report_to_s3(report_data: dict) -> str:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    date = report_data["order_date"]
    html = f"""<!DOCTYPE html>
<html>
<head><title>Daily Orders Report — {date}</title></head>
<body>
<h1>Daily Orders Report: {date}</h1>
<table border="1" cellpadding="8">
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Total Orders</td>      <td>{report_data['total_orders']}</td></tr>
  <tr><td>Total Revenue</td>     <td>${report_data['total_revenue']}</td></tr>
  <tr><td>Avg Order Value</td>   <td>${report_data['avg_order_value']}</td></tr>
  <tr><td>Unique Customers</td>  <td>{report_data['unique_customers']}</td></tr>
  <tr><td>Cancellations</td>     <td>{report_data['cancellations']}</td></tr>
</table>
</body>
</html>"""

    s3  = S3Hook(aws_conn_id="aws_default")
    key = f"daily/orders/{date}/report.html"
    s3.load_string(html, key=key, bucket_name="my-reports", replace=True)

    url = f"https://my-reports.s3.amazonaws.com/{key}"
    print(f"[write_report] Report published to {url}")
    return url


with DAG(
    dag_id="03_daily_order_report",
    description="Triggered by clean_orders_asset → generates and writes daily report",
    start_date=datetime(2024, 1, 1),
    schedule=[clean_orders_asset],  # ← Asset-based schedule: no cron
    catchup=False,
    default_args={"owner": "analytics"},
    tags=["event-driven", "consumer", "reporting"],
) as dag_report:
    report     = generate_report()
    report_url = write_report_to_s3(report_data=report)
