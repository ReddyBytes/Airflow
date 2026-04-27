"""
multi_source_etl_starter.py
===========================
Scaffold for the Multi-Source ETL Pipeline capstone.

Your job: implement the four TODO sections below.
Do NOT change the DAG ID, schedule, task names, or the SOURCES list structure.

Difficulty: Minimal Hints (some structure given, logic is yours to write)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from airflow.sdk import DAG, Asset, task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ── Source configuration ───────────────────────────────────────────────────────
# Each dict gets passed to extract_source as `source_config`.
# Add a 4th dict here and a new task instance appears automatically — no DAG changes needed.
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

# Asset emitted when the load task succeeds — triggers downstream pipelines
WAREHOUSE_ASSET = Asset("postgres://warehouse/multi_source_daily")


# ── Task 1: Extract ────────────────────────────────────────────────────────────

@task(
    retries=3,
    retry_delay=timedelta(seconds=30),
)
def extract_source(source_config: dict, ds: str | None = None) -> str:
    """
    Route to the correct extractor based on source_config["source_type"].
    Must return a JSON string (list of records).
    Each record must include "source_id" and "source_date" columns.

    TODO:
      - Handle source_type == "http": use requests.get(), flatten rates into rows
      - Handle source_type == "s3": use S3Hook, read CSV, add source columns
      - Handle source_type == "postgres": use PostgresHook.get_pandas_df(), add source columns
      - Raise ValueError for unknown source_type
    """
    stype = source_config["source_type"]
    source_id = source_config["source_id"]
    print(f"[extract_source] Extracting '{source_id}' for {ds}")

    # TODO: implement routing logic
    raise NotImplementedError("Implement extract_source routing")


# ── Task 2: Merge ──────────────────────────────────────────────────────────────

@task
def merge_sources(extracted_results: list[str]) -> str:
    """
    Concatenate all extracted JSON payloads into one DataFrame.
    Add an _extract_index column to preserve which task produced each slice.

    TODO:
      - Iterate extracted_results (each is a JSON string of records)
      - Parse each into a DataFrame
      - Concatenate all frames
      - Return merged.to_json(orient="records", date_format="iso")
    """
    # TODO: implement merge
    raise NotImplementedError("Implement merge_sources")


# ── Task 3: Validate ──────────────────────────────────────────────────────────

@task
def validate_merged(merged_json: str, ds: str | None = None) -> str:
    """
    Run quality checks on the merged DataFrame.

    Must raise ValueError if:
      - Zero rows after merge
      - "source_id" column is missing
      - Any "source_id" values are null

    Log warnings (but do not fail) for nulls in other columns.
    Return merged_json unchanged if all checks pass.

    TODO: implement validation rules
    """
    # TODO: implement validation
    raise NotImplementedError("Implement validate_merged")


# ── Task 4: Load ──────────────────────────────────────────────────────────────

@task(outlets=[WAREHOUSE_ASSET])
def load_to_warehouse(validated_json: str, ds: str | None = None) -> int:
    """
    Load merged data to warehouse.multi_source_daily.

    Must be idempotent:
      1. DELETE rows for source_date = ds
      2. INSERT all rows
      3. Confirm count and return it

    TODO: implement DELETE + INSERT pattern using PostgresHook
    """
    # TODO: implement idempotent load
    raise NotImplementedError("Implement load_to_warehouse")


# ── DAG assembly ──────────────────────────────────────────────────────────────

with DAG(
    dag_id="multi_source_etl",
    description="Parallel multi-source extract → merge → validate → load (Airflow 3)",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={
        "owner": "data-engineering",
    },
    tags=["capstone", "dynamic-mapping", "etl"],
) as dag:

    # TODO: wire the four tasks together using expand() for extract_source
    # Hint: extracted = extract_source.expand(source_config=SOURCES)
    pass
