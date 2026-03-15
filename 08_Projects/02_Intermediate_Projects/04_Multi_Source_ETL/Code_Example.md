# Multi-Source ETL — Full DAG Code

Complete Airflow 3 DAG using `@task` decorator and dynamic task mapping to pull from
REST API, S3, and Postgres in parallel, merge results, validate, and load to warehouse.

---

```python
"""
multi_source_etl.py
===================
Pulls data from three sources in parallel using dynamic task mapping,
merges the results, validates, and loads to the warehouse.

Required Airflow connections:
  - aws_default          : AWS credentials
  - postgres_source      : Source operational Postgres DB
  - postgres_warehouse   : Destination warehouse Postgres DB

Required Python packages:
  - pandas, requests
  - apache-airflow-providers-amazon
  - apache-airflow-providers-postgres
  - apache-airflow-providers-http
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import requests

from airflow.sdk import DAG, Asset, task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ── Source configuration ───────────────────────────────────────────────────────
# Adding a new source = adding one dict to this list.
# Dynamic task mapping handles the rest.
SOURCES: list[dict] = [
    {
        "source_id": "exchange_rates",
        "source_type": "http",
        "url": "https://api.exchangerate.host/latest?base=USD&symbols=EUR,GBP,JPY,CAD,AUD",
    },
    {
        "source_id": "product_catalogue",
        "source_type": "s3",
        "bucket": "my-data-lake",
        "key_template": "products/{ds}.csv",
    },
    {
        "source_id": "customer_orders",
        "source_type": "postgres",
        "conn_id": "postgres_source",
        "sql_template": "SELECT * FROM orders WHERE DATE(created_at) = '{ds}'",
    },
]

# Asset produced by the final load task — triggers downstream pipelines
WAREHOUSE_ASSET = Asset("postgres://warehouse/multi_source_daily")


# ── Extraction tasks (one per source via dynamic mapping) ─────────────────────

@task(
    retries=3,
    retry_delay=timedelta(seconds=30),
    doc_md="Extract data from a single source. Returns JSON string for XCom.",
)
def extract_source(source_config: dict, ds: str | None = None) -> str:
    """Route to the correct extractor based on source_type."""
    stype = source_config["source_type"]
    source_id = source_config["source_id"]
    print(f"[extract_source] Extracting '{source_id}' for {ds}")

    if stype == "http":
        resp = requests.get(source_config["url"], timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = [
            {"source_id": source_id, "currency": k, "rate": v, "date": ds}
            for k, v in data.get("rates", {}).items()
        ]
        print(f"[extract_source] {source_id}: {len(rows)} rate rows")
        return json.dumps(rows)

    elif stype == "s3":
        import io
        hook = S3Hook(aws_conn_id="aws_default")
        key = source_config["key_template"].format(ds=ds)
        content = hook.read_key(key, bucket_name=source_config["bucket"])
        df = pd.read_csv(io.StringIO(content))
        df.insert(0, "source_id", source_id)
        df.insert(1, "source_date", ds)
        print(f"[extract_source] {source_id}: {len(df)} rows from s3://{source_config['bucket']}/{key}")
        return df.to_json(orient="records")

    elif stype == "postgres":
        hook = PostgresHook(postgres_conn_id=source_config["conn_id"])
        sql = source_config["sql_template"].format(ds=ds)
        df = hook.get_pandas_df(sql)
        df.insert(0, "source_id", source_id)
        df.insert(1, "source_date", ds)
        print(f"[extract_source] {source_id}: {len(df)} rows from Postgres")
        return df.to_json(orient="records")

    else:
        raise ValueError(f"Unknown source_type: {stype!r}")


# ── Merge ─────────────────────────────────────────────────────────────────────

@task(doc_md="Stack all source DataFrames into one unified result.")
def merge_sources(extracted_results: list[str]) -> str:
    """
    Concatenate JSON payloads from all extract tasks.
    Each payload is a list of dicts (JSON records).
    """
    frames = []
    for idx, payload in enumerate(extracted_results):
        rows = json.loads(payload)
        df = pd.DataFrame(rows)
        df["_extract_index"] = idx
        frames.append(df)
        print(f"[merge_sources] Payload {idx}: {len(df)} rows, columns: {list(df.columns)}")

    merged = pd.concat(frames, ignore_index=True)
    print(f"[merge_sources] Total merged rows: {len(merged)}")
    return merged.to_json(orient="records", date_format="iso")


# ── Validate ──────────────────────────────────────────────────────────────────

@task(doc_md="Run basic quality checks on merged data. Fail task on critical issues.")
def validate_merged(merged_json: str, ds: str | None = None) -> str:
    """
    Validation rules:
    1. At least 1 row must exist.
    2. 'source_id' column must be present and fully populated.
    3. Log (but do not fail) on any other column nulls.
    """
    df = pd.DataFrame(json.loads(merged_json))

    errors: list[str] = []

    if len(df) == 0:
        errors.append("Zero rows after merge — all sources returned empty results")

    if "source_id" not in df.columns:
        errors.append("'source_id' column missing from merged data")
    elif df["source_id"].isnull().any():
        errors.append(f"{df['source_id'].isnull().sum()} rows have null source_id")

    # Warn (not fail) on other nulls
    for col in df.columns:
        null_count = df[col].isnull().sum()
        if null_count > 0:
            pct = null_count / len(df) * 100
            print(f"[validate] WARNING: {col} has {null_count} nulls ({pct:.1f}%)")

    if errors:
        raise ValueError(f"Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    print(f"[validate] PASSED: {len(df)} rows, {len(df.columns)} columns for {ds}")
    return merged_json


# ── Load ──────────────────────────────────────────────────────────────────────

@task(
    outlets=[WAREHOUSE_ASSET],
    doc_md="Load validated merged data to warehouse.multi_source_daily.",
)
def load_to_warehouse(validated_json: str, ds: str | None = None) -> int:
    """
    Truncate-and-insert for idempotency (daily partition).
    Uses outlets=[WAREHOUSE_ASSET] to signal downstream Asset consumers.
    """
    df = pd.DataFrame(json.loads(validated_json))
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")

    # Delete existing rows for this partition (idempotent re-runs)
    hook.run(
        "DELETE FROM warehouse.multi_source_daily WHERE source_date = %s",
        parameters=[ds],
    )

    # Insert all rows
    rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
    hook.insert_rows(
        table="warehouse.multi_source_daily",
        rows=rows,
        target_fields=list(df.columns),
        commit_every=1000,
    )

    # Confirm
    wh_count = hook.get_first(
        "SELECT COUNT(*) FROM warehouse.multi_source_daily WHERE source_date = %s",
        parameters=[ds],
    )[0]
    print(f"[load] {wh_count} rows in warehouse.multi_source_daily for {ds}")
    return wh_count


# ── DAG assembly ──────────────────────────────────────────────────────────────

with DAG(
    dag_id="multi_source_etl",
    description="Parallel multi-source extract → merge → validate → load (Airflow 3)",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={
        "owner": "data-engineering",
        "email_on_failure": True,
        "email": "data-team@company.com",
    },
    tags=["intermediate", "dynamic-mapping", "etl", "airflow-3"],
    doc_md="""
    ## Multi-Source ETL Pipeline

    Demonstrates Airflow 3 dynamic task mapping for parallel extraction from:
    - REST API (exchange rates)
    - S3 (product catalogue CSV)
    - Postgres (customer orders)

    Merged result is validated and loaded to the warehouse. Produces
    `WAREHOUSE_ASSET` to trigger downstream consumers.
    """,
) as dag:

    # Fan-out: 3 extract tasks in parallel (one per source in SOURCES list)
    extracted = extract_source.expand(source_config=SOURCES)

    # Merge all 3 results into one DataFrame
    merged = merge_sources(extracted_results=extracted)

    # Validate
    validated = validate_merged(merged_json=merged)

    # Load — emits WAREHOUSE_ASSET on success
    load_to_warehouse(validated_json=validated)
```

---

## Warehouse Table DDL

Run this once before the first pipeline execution:

```sql
CREATE SCHEMA IF NOT EXISTS warehouse;

CREATE TABLE IF NOT EXISTS warehouse.multi_source_daily (
    source_id       TEXT,
    source_date     DATE,
    _extract_index  INTEGER,
    -- Additional columns vary by source; use a flexible schema:
    data            JSONB,
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msd_source_date
    ON warehouse.multi_source_daily (source_date);
```

For a typed schema (recommended for production), create separate destination tables
per source and route in the load task based on `source_id`.

---

## Trigger and Observe

```bash
# Trigger manually
airflow dags trigger multi_source_etl --exec-date 2024-01-15

# In the UI: Graph view shows 3x extract_source tasks mapped [0], [1], [2]
# Click "Mapped Tasks" on extract_source to see per-source logs
```

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Step-by-Step** | [Step_by_Step.md](./Step_by_Step.md) |
| **Parent: Intermediate Projects** | [02_Intermediate_Projects](../Readme.md) |
| **Next: ML Training Pipeline** | [05_ML_Training_Pipeline](../../03_Advanced_Projects/05_ML_Training_Pipeline/Project_Guide.md) |
