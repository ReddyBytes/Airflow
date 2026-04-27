"""
csv_file_processing_starter.py
================================
Project 02 — Simple File Processing Pipeline (Beginner+) — STARTER FILE

Fill in every section marked TODO. This project is partially guided —
use the hints in 03_GUIDE.md when you're stuck.

No external services needed. Everything uses local files.
Airflow 3 (airflow.sdk imports).
"""

import os
import shutil
import glob
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.sensors.filesystem import FileSensor

# ── Directory constants ───────────────────────────────────────────────────────
LANDING_DIR = "/tmp/landing"
PROCESSED_DIR = "/tmp/processed"
QUARANTINE_DIR = "/tmp/quarantine"

# ── Validation rules ──────────────────────────────────────────────────────────
REQUIRED_COLUMNS = {"tracking_number", "origin", "destination", "weight_kg", "status"}
VALID_STATUSES = {"pending", "in_transit", "delivered", "returned", "cancelled"}
MAX_ERROR_RATE = 0.50   # quarantine if more than 50% of rows are bad

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

# ── DAG ───────────────────────────────────────────────────────────────────────
with DAG(
    dag_id="csv_file_processing",
    description="Wait for CSV drop, validate, route to processed or quarantine",
    start_date=datetime(2024, 1, 1),
    schedule="*/30 8-11 * * 1-5",  # TODO: what does this schedule mean?
    catchup=False,
    default_args=default_args,
    tags=["beginner", "file-processing", "sensor"],
) as dag:

    # ── Task 1: Wait for the CSV file ─────────────────────────────────────────
    # TODO: Create a FileSensor that:
    #   - watches LANDING_DIR for "shipments_*.csv"
    #   - uses fs_conn_id="fs_default"
    #   - uses mode="reschedule" (why is this important?)
    #   - poke_interval=30, timeout=7200 (2 hours)
    wait_for_csv = FileSensor(
        task_id="wait_for_csv",
        # TODO: fill in parameters
    )

    # ── Task 2: Read and validate the CSV ─────────────────────────────────────
    def validate_csv(**context) -> Dict[str, Any]:
        """
        Load the CSV, run validation checks, push a report dict to XCom.

        TODO:
        1. Use glob.glob to find "shipments_*.csv" in LANDING_DIR
        2. Load the newest file with pd.read_csv()
        3. Check for missing required columns — raise ValueError if any missing
        4. Run 4 row-level checks (null tracking, null origin, invalid status, bad weight)
        5. Build a validation_report dict with these keys:
               file, csv_path, total_rows, valid_rows, invalid_rows, error_rate, issues, passed
        6. Push "validation_report" and "csv_path" to XCom
        7. Return the report dict
        """
        # TODO: implement this function
        pass

    validate = PythonOperator(
        task_id="validate_csv",
        python_callable=validate_csv,
    )

    # ── Task 3: Branch on validation result ───────────────────────────────────
    def decide_route(**context) -> str:
        """
        TODO:
        - Pull "validation_report" from XCom (task_ids="validate_csv")
        - Return "process_valid_rows" if report["passed"] is True
        - Return "quarantine_file" otherwise
        """
        # TODO: implement this function
        pass

    branch = BranchPythonOperator(
        task_id="branch_on_result",
        python_callable=decide_route,
    )

    # ── Task 4A: Process valid rows ───────────────────────────────────────────
    def process_valid_rows(**context) -> int:
        """
        TODO:
        1. Pull "validation_report" from XCom
        2. Load the CSV with pd.read_csv(report["csv_path"])
        3. Build a set of bad row indices from report["issues"]
           (hint: issue["row"] - 2 converts 1-indexed row numbers to 0-indexed)
        4. Drop those indices: valid_df = df.drop(index=..., errors="ignore")
        5. Print stats (status distribution, average weight)
        6. Push "rows_processed" to XCom
        7. Return len(valid_df)
        """
        # TODO: implement this function
        pass

    process = PythonOperator(
        task_id="process_valid_rows",
        python_callable=process_valid_rows,
    )

    # ── Task 4B: Move bad file to quarantine ──────────────────────────────────
    # TODO: Create a BashOperator that moves the CSV to QUARANTINE_DIR.
    # Use {{ ti.xcom_pull(task_ids='validate_csv', key='csv_path') }} to get the path.
    quarantine = BashOperator(
        task_id="quarantine_file",
        bash_command="""
            # TODO: write the mv command here using the XCom template
        """,
    )

    # ── Task 5A: Move processed file to archive ───────────────────────────────
    # TODO: Same pattern as quarantine, but move to PROCESSED_DIR instead.
    move_to_processed = BashOperator(
        task_id="move_to_processed",
        bash_command="""
            # TODO: write the mv command here
        """,
    )

    # ── Task 6: Log summary ───────────────────────────────────────────────────
    def log_summary(**context):
        """
        TODO:
        1. Pull "validation_report" from XCom
        2. Pull "rows_processed" from "process_valid_rows" (may be None on quarantine path)
        3. Print a formatted summary: file name, counts, error rate, outcome
        """
        # TODO: implement this function
        pass

    # TODO: set trigger_rule="none_failed_min_one_success" — why is this needed?
    summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
        # TODO: add trigger_rule here
    )

    # ── Task dependencies ─────────────────────────────────────────────────────
    # TODO: wire all tasks.
    # Remember: branch goes to EITHER process OR quarantine, then both reach summary.
    #
    # Sketch:
    # wait_for_csv → validate → branch ─┬─ process → move_to_processed ─┐
    #                                    │                                ├─ summary
    #                                    └─ quarantine ───────────────────┘
