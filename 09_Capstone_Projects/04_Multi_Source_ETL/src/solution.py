"""
multi_source_etl_solution.py
============================
Complete working Airflow 3 DAG.

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
# Dynamic task mapping handles the rest — no DAG code change needed.
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
        "key_template": "products/{ds}.csv",   # ← {ds} substituted at runtime
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


# ── Task 1: Extract ────────────────────────────────────────────────────────────

@task(
    retries=3,
    retry_delay=timedelta(seconds=30),
    doc_md="Extract data from a single source. Returns JSON string for XCom.",
)
def extract_source(source_config: dict, ds: str | None = None) -> str:
    """Route to the correct extractor based on source_type."""
    stype     = source_config["source_type"]
    source_id = source_config["source_id"]
    print(f"[extract_source] Extracting '{source_id}' for {ds}")

    if stype == "http":
        resp = requests.get(source_config["url"], timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Flatten exchange rate map into one row per currency
        rows = [
            {"source_id": source_id, "source_date": ds, "currency": k, "rate": v}
            for k, v in data.get("rates", {}).items()
        ]
        print(f"[extract_source] {source_id}: {len(rows)} rate rows")
        return json.dumps(rows)

    elif stype == "s3":
        import io
        hook    = S3Hook(aws_conn_id="aws_default")
        key     = source_config["key_template"].format(ds=ds)   # ← substitute date
        content = hook.read_key(key, bucket_name=source_config["bucket"])
        df      = pd.read_csv(io.StringIO(content))
        df.insert(0, "source_id",   source_id)
        df.insert(1, "source_date", ds)
        print(f"[extract_source] {source_id}: {len(df)} rows from s3://{source_config['bucket']}/{key}")
        return df.to_json(orient="records")

    elif stype == "postgres":
        hook = PostgresHook(postgres_conn_id=source_config["conn_id"])
        sql  = source_config["sql_template"].format(ds=ds)      # ← substitute date
        df   = hook.get_pandas_df(sql)
        df.insert(0, "source_id",   source_id)
        df.insert(1, "source_date", ds)
        print(f"[extract_source] {source_id}: {len(df)} rows from Postgres")
        return df.to_json(orient="records")

    else:
        raise ValueError(f"Unknown source_type: {stype!r}")


# ── Task 2: Merge ──────────────────────────────────────────────────────────────

@task(doc_md="Stack all source DataFrames into one unified result.")
def merge_sources(extracted_results: list[str]) -> str:
    """
    Concatenate JSON payloads from all extract tasks.
    extracted_results is a list of JSON strings — one per mapped task instance.
    """
    frames = []
    for idx, payload in enumerate(extracted_results):
        rows = json.loads(payload)
        df   = pd.DataFrame(rows)
        df["_extract_index"] = idx   # ← preserve which source index produced this slice
        frames.append(df)
        print(f"[merge_sources] Payload {idx}: {len(df)} rows, columns: {list(df.columns)}")

    merged = pd.concat(frames, ignore_index=True)
    print(f"[merge_sources] Total merged rows: {len(merged)}")
    return merged.to_json(orient="records", date_format="iso")


# ── Task 3: Validate ──────────────────────────────────────────────────────────

@task(doc_md="Run basic quality checks on merged data. Fail task on critical issues.")
def validate_merged(merged_json: str, ds: str | None = None) -> str:
    """
    Validation rules:
      1. At least 1 row must exist.
      2. 'source_id' column must be present and fully populated.
      3. Log warnings (not failures) for nulls in any other column.
    """
    df = pd.DataFrame(json.loads(merged_json))

    errors: list[str] = []

    if len(df) == 0:
        errors.append("Zero rows after merge — all sources returned empty results")

    if "source_id" not in df.columns:
        errors.append("'source_id' column missing from merged data")
    elif df["source_id"].isnull().any():
        errors.append(f"{df['source_id'].isnull().sum()} rows have null source_id")

    # Warn on other nulls — not a hard failure
    for col in df.columns:
        null_count = df[col].isnull().sum()
        if null_count > 0:
            pct = null_count / len(df) * 100
            print(f"[validate] WARNING: {col} has {null_count} nulls ({pct:.1f}%)")

    if errors:
        raise ValueError("Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    print(f"[validate] PASSED: {len(df)} rows, {len(df.columns)} columns for {ds}")
    return merged_json  # ← pass through unchanged


# ── Task 4: Load ──────────────────────────────────────────────────────────────

@task(
    outlets=[WAREHOUSE_ASSET],   # ← emits asset when task succeeds
    doc_md="Load validated merged data to warehouse.multi_source_daily.",
)
def load_to_warehouse(validated_json: str, ds: str | None = None) -> int:
    """
    DELETE existing rows for this partition, then INSERT fresh rows.
    Idempotent: safe to rerun for the same execution date.
    """
    df   = pd.DataFrame(json.loads(validated_json))
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

    # Confirm row count
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
    tags=["capstone", "dynamic-mapping", "etl", "airflow-3"],
    doc_md="""
    ## Multi-Source ETL Pipeline

    Extracts from REST API, S3, and Postgres in parallel using dynamic task mapping.
    Merges, validates, and loads to warehouse. Emits WAREHOUSE_ASSET on success.
    """,
) as dag:

    # Fan-out: one extract_source task instance per source config
    extracted = extract_source.expand(source_config=SOURCES)

    # Merge: receives list of 3 JSON strings, one per mapped task instance
    merged = merge_sources(extracted_results=extracted)

    # Validate
    validated = validate_merged(merged_json=merged)

    # Load — emits WAREHOUSE_ASSET on success
    load_to_warehouse(validated_json=validated)
