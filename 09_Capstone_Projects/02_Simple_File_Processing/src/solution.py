"""
csv_file_processing_solution.py
=================================
Project 02 — Simple File Processing Pipeline (Beginner+) — COMPLETE SOLUTION

Watches a landing folder for a vendor's CSV, validates content,
routes to process or quarantine based on error rate, and logs a summary.

No external services. Airflow 3 (airflow.sdk imports).
"""

import os
import glob
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
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
    schedule="*/30 8-11 * * 1-5",  # ← every 30 min, 8–11am, weekdays
    catchup=False,
    default_args=default_args,
    tags=["beginner", "file-processing", "sensor"],
) as dag:

    # ── Task 1: Wait for the CSV file ─────────────────────────────────────────
    # FileSensor polls the landing directory every 30 s.
    # mode="reschedule" releases the worker slot while waiting.
    wait_for_csv = FileSensor(
        task_id="wait_for_csv",
        filepath=f"{LANDING_DIR}/shipments_*.csv",
        fs_conn_id="fs_default",
        poke_interval=30,
        timeout=7200,               # give up after 2 hours
        mode="reschedule",          # ← don't hold a worker slot while waiting
    )

    # ── Task 2: Validate the CSV ──────────────────────────────────────────────
    def validate_csv(**context) -> Dict[str, Any]:
        """
        Find the CSV, run 6 validation checks, build a report, push to XCom.

        The report dict is the single source of truth for all downstream tasks.
        """
        # Find the newest CSV in the landing directory
        files = sorted(glob.glob(f"{LANDING_DIR}/shipments_*.csv"))
        if not files:
            raise FileNotFoundError(f"No shipments CSV in {LANDING_DIR}")

        csv_path = max(files, key=os.path.getmtime)   # most recently modified
        filename = Path(csv_path).name
        print(f"Processing: {csv_path}")

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise ValueError(f"Cannot read CSV: {e}")

        total_rows = len(df)
        if total_rows == 0:
            raise ValueError("CSV is empty")

        # ── Check 1: required columns ────────────────────────────────────────
        missing_cols = REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        issues = []

        # ── Check 2: no null tracking numbers ────────────────────────────────
        for idx, row in df[df["tracking_number"].isna()].iterrows():
            issues.append({
                "row": int(idx) + 2,        # +2 converts 0-index to 1-index + header
                "column": "tracking_number",
                "error": "null value — required field",
            })

        # ── Check 3: no null origins ──────────────────────────────────────────
        for idx, row in df[df["origin"].isna()].iterrows():
            issues.append({
                "row": int(idx) + 2,
                "column": "origin",
                "error": "null value",
            })

        # ── Check 4: valid status values ──────────────────────────────────────
        for idx, row in df[~df["status"].isin(VALID_STATUSES)].iterrows():
            issues.append({
                "row": int(idx) + 2,
                "column": "status",
                "error": f"invalid value '{row['status']}' — must be in {VALID_STATUSES}",
            })

        # ── Check 5: positive weight ──────────────────────────────────────────
        try:
            df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="raise")
            for idx, row in df[df["weight_kg"] <= 0].iterrows():
                issues.append({
                    "row": int(idx) + 2,
                    "column": "weight_kg",
                    "error": f"weight must be positive, got {row['weight_kg']}",
                })
        except (ValueError, TypeError):
            issues.append({
                "row": "multiple",
                "column": "weight_kg",
                "error": "column contains non-numeric values",
            })

        # ── Calculate error rate ──────────────────────────────────────────────
        # Count unique bad row numbers (one row can trigger multiple checks)
        bad_row_numbers = {i["row"] for i in issues if isinstance(i["row"], int)}
        bad_row_count = len(bad_row_numbers)
        error_rate = bad_row_count / total_rows

        validation_report = {
            "file": filename,
            "csv_path": csv_path,
            "total_rows": total_rows,
            "valid_rows": total_rows - bad_row_count,
            "invalid_rows": bad_row_count,
            "error_rate": round(error_rate, 4),
            "issues": issues,
            "passed": error_rate < MAX_ERROR_RATE,
        }

        # Push to XCom — multiple downstream tasks will read this
        context["ti"].xcom_push(key="validation_report", value=validation_report)
        context["ti"].xcom_push(key="csv_path", value=csv_path)

        print(f"Validation: {validation_report['valid_rows']}/{total_rows} rows valid "
              f"(error rate {error_rate:.1%})")
        return validation_report

    validate = PythonOperator(
        task_id="validate_csv",
        python_callable=validate_csv,
    )

    # ── Task 3: Branch on validation result ───────────────────────────────────
    def decide_route(**context) -> str:
        """
        Read the validation report and return the task_id to execute.
        Airflow marks the other branch as "skipped".
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")

        if report["passed"]:
            print(f"Validation passed — routing to process_valid_rows")
            return "process_valid_rows"
        else:
            print(
                f"Validation failed — error rate {report['error_rate']:.1%} "
                f"exceeds threshold {MAX_ERROR_RATE:.1%}. Quarantining."
            )
            return "quarantine_file"

    branch = BranchPythonOperator(
        task_id="branch_on_result",
        python_callable=decide_route,
    )

    # ── Task 4A: Process valid rows ───────────────────────────────────────────
    def process_valid_rows(**context) -> int:
        """
        Load the CSV, filter to valid rows only, and process them.
        In production this would write to a DB or downstream system.
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
        df = pd.read_csv(report["csv_path"])

        # Convert issue row numbers (1-indexed) back to DataFrame indices (0-indexed)
        bad_indices = {
            issue["row"] - 2
            for issue in report["issues"]
            if isinstance(issue["row"], int)
        }
        valid_df = df.drop(index=list(bad_indices), errors="ignore")

        print(f"Processing {len(valid_df)} valid rows...")
        print(f"Status distribution:\n{valid_df['status'].value_counts().to_string()}")
        print(f"Average weight: {valid_df['weight_kg'].mean():.2f} kg")

        # In production: valid_df.to_sql(...) or write to S3 here

        context["ti"].xcom_push(key="rows_processed", value=len(valid_df))
        return len(valid_df)

    process = PythonOperator(
        task_id="process_valid_rows",
        python_callable=process_valid_rows,
    )

    # ── Task 4B: Quarantine bad file ──────────────────────────────────────────
    # BashOperator is sufficient — we just need an `mv` command.
    quarantine = BashOperator(
        task_id="quarantine_file",
        bash_command="""
            CSV_PATH="{{ ti.xcom_pull(task_ids='validate_csv', key='csv_path') }}"
            FILENAME=$(basename "$CSV_PATH")
            DEST="{{ params.quarantine_dir }}/${FILENAME}"

            echo "Quarantining: $CSV_PATH → $DEST"
            mv "$CSV_PATH" "$DEST"
            echo "Done."
        """,
        params={"quarantine_dir": QUARANTINE_DIR},
    )

    # ── Task 5A: Archive the processed file ───────────────────────────────────
    move_to_processed = BashOperator(
        task_id="move_to_processed",
        bash_command="""
            CSV_PATH="{{ ti.xcom_pull(task_ids='validate_csv', key='csv_path') }}"
            FILENAME=$(basename "$CSV_PATH")
            DEST="{{ params.processed_dir }}/${FILENAME}"

            echo "Archiving: $CSV_PATH → $DEST"
            mv "$CSV_PATH" "$DEST"
        """,
        params={"processed_dir": PROCESSED_DIR},
    )

    # ── Task 6: Log summary (runs after either branch) ────────────────────────
    def log_summary(**context):
        """
        Print a unified summary of the run.
        trigger_rule="none_failed_min_one_success" ensures this runs after
        whichever branch completed.
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
        rows_processed = context["ti"].xcom_pull(
            task_ids="process_valid_rows", key="rows_processed"
        ) or 0

        print("=" * 60)
        print(f"CSV PROCESSING SUMMARY — {context['ds']}")
        print("=" * 60)
        print(f"File         : {report['file']}")
        print(f"Total rows   : {report['total_rows']}")
        print(f"Valid rows   : {report['valid_rows']}")
        print(f"Invalid rows : {report['invalid_rows']}")
        print(f"Error rate   : {report['error_rate']:.1%}")
        print(f"Outcome      : {'PROCESSED' if report['passed'] else 'QUARANTINED'}")
        if rows_processed:
            print(f"Rows written : {rows_processed}")
        if report["issues"]:
            print(f"\nIssues ({len(report['issues'])} total):")
            for issue in report["issues"][:10]:     # show first 10
                print(f"  Row {issue['row']}: {issue['column']} — {issue['error']}")
        print("=" * 60)

    # trigger_rule ensures this task runs after EITHER branch completes,
    # not just when the process branch runs.
    summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
        trigger_rule="none_failed_min_one_success",
    )

    # ── Task dependencies ─────────────────────────────────────────────────────
    #
    # wait_for_csv → validate → branch ─┬─ process → move_to_processed ─┐
    #                                    │                                ├─ summary
    #                                    └─ quarantine ───────────────────┘
    #
    wait_for_csv >> validate >> branch
    branch >> process >> move_to_processed >> summary
    branch >> quarantine >> summary
