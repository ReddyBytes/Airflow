# 🟢 CSV File Processing Pipeline — Complete DAG Code

Complete, well-commented Airflow 3 DAG. Copy to your `dags/` directory.

```python
"""
csv_file_processing.py
======================
Project 02 — CSV File Processing Pipeline (Beginner)

Watches a landing folder for a CSV file, validates its content,
branches based on quality, moves the file to processed or quarantine,
and logs a summary report.

No external services needed — everything uses local files.
Airflow 3 syntax (airflow.sdk imports).
"""

import os
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.sensors.filesystem import FileSensor

# ── Directory constants ──────────────────────────────────────────
LANDING_DIR = "/tmp/landing"
PROCESSED_DIR = "/tmp/processed"
QUARANTINE_DIR = "/tmp/quarantine"

# Pattern to match: shipments_YYYYMMDD.csv
# Sensor monitors the landing dir; we find the file in the validate task
FILE_PATTERN = "shipments_*.csv"

# ── Validation rules ─────────────────────────────────────────────
REQUIRED_COLUMNS = {"tracking_number", "origin", "destination", "weight_kg", "status"}
VALID_STATUSES = {"pending", "in_transit", "delivered", "returned", "cancelled"}
MAX_ERROR_RATE = 0.50   # quarantine if more than 50% of rows are bad

# ── Default args ─────────────────────────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

# ── DAG definition ───────────────────────────────────────────────
with DAG(
    dag_id="csv_file_processing",
    description="Wait for CSV drop, validate, route to processed or quarantine",
    start_date=datetime(2024, 1, 1),
    schedule="*/30 8-11 * * 1-5",   # Every 30 min, 8am–11am, weekdays
    catchup=False,
    default_args=default_args,
    tags=["beginner", "file-processing", "sensor"],
) as dag:

    # ── Task 1: Wait for the CSV file ────────────────────────────
    # FileSensor polls the landing directory until a matching file appears
    # mode="reschedule" releases the worker slot while waiting
    # — critical for production to avoid blocking other tasks
    wait_for_csv = FileSensor(
        task_id="wait_for_csv",
        filepath=f"{LANDING_DIR}/{FILE_PATTERN}",
        poke_interval=30,           # check every 30 seconds
        timeout=7200,               # give up after 2 hours (9am + 2hr = 11am)
        mode="reschedule",          # don't block a worker while waiting
    )

    # ── Task 2: Read and validate the CSV ────────────────────────
    def validate_csv(**context) -> Dict[str, Any]:
        """
        Read the CSV file, run validation checks, push report to XCom.

        Checks performed:
          1. File exists and is readable
          2. Required columns are present
          3. No null tracking numbers (critical field)
          4. Status values are in the allowed set
          5. Weight is positive numeric
          6. Row count > 0

        Returns a dict with validation results pushed to XCom.
        """
        import glob

        # Find the CSV file in the landing dir
        files = sorted(glob.glob(f"{LANDING_DIR}/shipments_*.csv"))
        if not files:
            raise FileNotFoundError(f"No shipments CSV found in {LANDING_DIR}")

        # Process the most recently modified file
        csv_path = max(files, key=os.path.getmtime)
        filename = Path(csv_path).name
        print(f"Processing file: {csv_path}")

        # ── Load the CSV ─────────────────────────────────────────
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            raise ValueError(f"Cannot read CSV: {e}")

        issues = []
        total_rows = len(df)

        if total_rows == 0:
            raise ValueError("CSV file is empty — nothing to process")

        # ── Check 1: Required columns present ───────────────────
        missing_cols = REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            raise ValueError(
                f"Missing required columns: {missing_cols}. "
                f"Found: {list(df.columns)}"
            )

        # ── Check 2: Null tracking numbers ───────────────────────
        null_tracking = df[df["tracking_number"].isna()]
        for idx, row in null_tracking.iterrows():
            issues.append({
                "row": int(idx) + 2,        # +2 for 1-index + header
                "column": "tracking_number",
                "error": "null value — tracking number is required",
            })

        # ── Check 3: Null origins ─────────────────────────────────
        null_origin = df[df["origin"].isna()]
        for idx, row in null_origin.iterrows():
            issues.append({
                "row": int(idx) + 2,
                "column": "origin",
                "error": "null value",
            })

        # ── Check 4: Invalid status values ───────────────────────
        invalid_status = df[~df["status"].isin(VALID_STATUSES)]
        for idx, row in invalid_status.iterrows():
            issues.append({
                "row": int(idx) + 2,
                "column": "status",
                "error": f"invalid value '{row['status']}' — must be one of {VALID_STATUSES}",
            })

        # ── Check 5: Weight must be positive ─────────────────────
        # First, check if weight_kg is numeric
        try:
            df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="raise")
            negative_weight = df[df["weight_kg"] <= 0]
            for idx, row in negative_weight.iterrows():
                issues.append({
                    "row": int(idx) + 2,
                    "column": "weight_kg",
                    "error": f"weight must be positive, got {row['weight_kg']}",
                })
        except (ValueError, TypeError):
            issues.append({
                "row": "multiple",
                "column": "weight_kg",
                "error": "weight_kg column contains non-numeric values",
            })

        # ── Calculate error rate ──────────────────────────────────
        # Count unique bad rows (a row can have multiple issues)
        bad_row_numbers = {issue["row"] for issue in issues if issue["row"] != "multiple"}
        bad_row_count = len(bad_row_numbers)
        valid_row_count = total_rows - bad_row_count
        error_rate = bad_row_count / total_rows if total_rows > 0 else 0

        validation_report = {
            "file": filename,
            "csv_path": csv_path,
            "total_rows": total_rows,
            "valid_rows": valid_row_count,
            "invalid_rows": bad_row_count,
            "error_rate": round(error_rate, 4),
            "issues": issues,
            "passed": error_rate < MAX_ERROR_RATE,
        }

        # Push to XCom so downstream tasks can access the report
        context["ti"].xcom_push(key="validation_report", value=validation_report)
        context["ti"].xcom_push(key="csv_path", value=csv_path)

        print(f"Validation complete: {valid_row_count}/{total_rows} rows valid")
        if issues:
            print(f"Issues found: {len(issues)}")
            for issue in issues[:5]:        # print first 5 issues
                print(f"  Row {issue['row']}: {issue['column']} — {issue['error']}")

        return validation_report

    validate = PythonOperator(
        task_id="validate_csv",
        python_callable=validate_csv,
    )

    # ── Task 3: Branch based on validation result ─────────────────
    def decide_route(**context) -> str:
        """
        Read the validation report from XCom.
        Return the task_id to execute next.
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")

        if report["passed"]:
            print(f"Validation passed — routing to process_valid_rows")
            return "process_valid_rows"
        else:
            print(
                f"Validation failed — error rate {report['error_rate']:.1%} "
                f"exceeds threshold {MAX_ERROR_RATE:.1%}"
            )
            return "quarantine_file"

    branch = BranchPythonOperator(
        task_id="branch_on_result",
        python_callable=decide_route,
    )

    # ── Task 4A: Process valid rows ───────────────────────────────
    def process_valid_rows(**context) -> int:
        """
        Load the CSV, filter to only valid rows, and process them.
        In a real pipeline, this would write to a database or downstream system.
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
        csv_path = report["csv_path"]

        df = pd.read_csv(csv_path)

        # Keep only rows without issues
        bad_rows = {issue["row"] - 2 for issue in report["issues"]
                    if isinstance(issue["row"], int)}
        valid_df = df.drop(index=list(bad_rows), errors="ignore")

        print(f"Processing {len(valid_df)} valid rows...")

        # ── Your business logic here ──────────────────────────────
        # Examples:
        #   valid_df.to_sql("shipments", engine, if_exists="append")
        #   valid_df.to_parquet(f"s3://bucket/shipments/{context['ds']}.parquet")

        # For this example, we'll just log the stats
        print(f"Status distribution:\n{valid_df['status'].value_counts().to_string()}")
        print(f"Average weight: {valid_df['weight_kg'].mean():.2f} kg")

        context["ti"].xcom_push(key="rows_processed", value=len(valid_df))
        return len(valid_df)

    process = PythonOperator(
        task_id="process_valid_rows",
        python_callable=process_valid_rows,
    )

    # ── Task 4B: Quarantine bad file ──────────────────────────────
    # BashOperator moves the file to the quarantine folder
    # The filename is preserved so the vendor can identify it
    quarantine = BashOperator(
        task_id="quarantine_file",
        bash_command="""
            CSV_PATH="{{ ti.xcom_pull(task_ids='validate_csv', key='csv_path') }}"
            FILENAME=$(basename "$CSV_PATH")
            DEST="{{ params.quarantine_dir }}/${FILENAME}"

            echo "Moving $CSV_PATH to quarantine: $DEST"
            mv "$CSV_PATH" "$DEST"
            echo "File quarantined: $DEST"
        """,
        params={"quarantine_dir": QUARANTINE_DIR},
    )

    # ── Task 5A: Move processed file to archive ───────────────────
    move_to_processed = BashOperator(
        task_id="move_to_processed",
        bash_command="""
            CSV_PATH="{{ ti.xcom_pull(task_ids='validate_csv', key='csv_path') }}"
            FILENAME=$(basename "$CSV_PATH")
            DEST="{{ params.processed_dir }}/${FILENAME}"

            echo "Archiving to: $DEST"
            mv "$CSV_PATH" "$DEST"
        """,
        params={"processed_dir": PROCESSED_DIR},
    )

    # ── Task 6: Log summary (runs regardless of which branch) ─────
    def log_summary(**context):
        """
        Log a summary of what happened. Runs after either branch.
        trigger_rule="none_failed_min_one_success" ensures this
        runs after whichever branch completed.
        """
        report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
        rows_processed = context["ti"].xcom_pull(
            task_ids="process_valid_rows", key="rows_processed"
        ) or 0

        print("=" * 60)
        print(f"CSV PROCESSING SUMMARY — {context['ds']}")
        print("=" * 60)
        print(f"File:          {report['file']}")
        print(f"Total rows:    {report['total_rows']}")
        print(f"Valid rows:    {report['valid_rows']}")
        print(f"Invalid rows:  {report['invalid_rows']}")
        print(f"Error rate:    {report['error_rate']:.1%}")
        print(f"Outcome:       {'PROCESSED' if report['passed'] else 'QUARANTINED'}")
        if rows_processed:
            print(f"Rows written:  {rows_processed}")
        if report["issues"]:
            print(f"\nIssues ({len(report['issues'])} total):")
            for issue in report["issues"]:
                print(f"  Row {issue['row']}: {issue['column']} — {issue['error']}")
        print("=" * 60)

    summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
        # Run regardless of which branch was taken
        trigger_rule="none_failed_min_one_success",
    )

    # ── Task dependencies ─────────────────────────────────────────
    #
    # wait_for_csv → validate → branch ─┬─ process → move_to_processed ─┐
    #                                    │                                ├─ summary
    #                                    └─ quarantine ───────────────────┘
    #
    wait_for_csv >> validate >> branch
    branch >> process >> move_to_processed >> summary
    branch >> quarantine >> summary
```

---

## How to Test

```bash
# 1. Set up folders
mkdir -p /tmp/landing /tmp/processed /tmp/quarantine

# 2. Create a test CSV
cat > /tmp/landing/shipments_$(date +%Y%m%d).csv << 'EOF'
tracking_number,origin,destination,weight_kg,status
TRK001,New York,Los Angeles,12.5,in_transit
TRK002,Chicago,Miami,3.2,delivered
TRK003,Seattle,Boston,8.9,pending
TRK004,,Dallas,5.1,in_transit
TRK005,Atlanta,Denver,2.0,delivered
EOF

# 3. Trigger the DAG
airflow dags trigger csv_file_processing

# 4. Check results
ls /tmp/processed/   # should show the moved CSV
ls /tmp/quarantine/  # should be empty (error rate 20% < threshold 50%)
```

**To test quarantine path:** make 3 out of 5 rows have null tracking numbers:
```bash
cat > /tmp/landing/shipments_$(date +%Y%m%d).csv << 'EOF'
tracking_number,origin,destination,weight_kg,status
TRK001,New York,LA,12.5,in_transit
,Chicago,Miami,3.2,delivered
,Seattle,Boston,8.9,pending
,Dallas,Houston,5.1,in_transit
TRK005,Atlanta,Denver,2.0,delivered
EOF
# 3/5 = 60% error rate → quarantine
```
