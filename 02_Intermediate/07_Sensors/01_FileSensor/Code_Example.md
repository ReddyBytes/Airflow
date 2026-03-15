# FileSensor — Code Examples

## Example 1: Wait for a Single File

The simplest use case — wait for one specific file before processing begins.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.filesystem import FileSensor
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="filesensor_single_file",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 6 * * *",   # Every day at 6am
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["sensor", "file", "example"],
) as dag:

    # STEP 1: Wait for the vendor's daily CSV to appear
    # The file name includes today's date in YYYYMMDD format
    wait_for_vendor_csv = FileSensor(
        task_id="wait_for_vendor_delivery",
        filepath="/data/incoming/vendor_orders_{{ ds_nodash }}.csv",
        # ds_nodash = execution date without dashes: 20240115
        fs_conn_id="fs_default",         # Default local filesystem connection
        poke_interval=60,                # Check every 60 seconds
        timeout=6 * 60 * 60,             # Give up after 6 hours
        mode="reschedule",               # Release worker slot between pokes
        soft_fail=False,                 # Hard fail if timeout exceeded
    )

    # STEP 2: Validate the file after it appears
    def validate_csv_file(**context):
        import csv
        date_nodash = context["ds_nodash"]
        filepath = f"/data/incoming/vendor_orders_{date_nodash}.csv"

        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"File has {len(rows)} rows")

        # Check required columns exist
        if rows:
            required_cols = {"order_id", "customer_id", "amount", "date"}
            actual_cols = set(rows[0].keys())
            missing = required_cols - actual_cols
            if missing:
                raise ValueError(f"Missing columns: {missing}")

        # Check it's not empty
        if len(rows) == 0:
            raise ValueError("File is empty — no rows to process")

        print(f"Validation passed: {len(rows)} valid rows")
        return len(rows)

    validate_file = PythonOperator(
        task_id="validate_file",
        python_callable=validate_csv_file,
    )

    # STEP 3: Process the validated file
    process_file = BashOperator(
        task_id="process_vendor_file",
        bash_command="""
            echo "Processing vendor file for {{ ds }}"
            python3 /opt/airflow/scripts/process_vendor.py \
                --input /data/incoming/vendor_orders_{{ ds_nodash }}.csv \
                --output /data/processed/{{ ds }}/vendor_orders.parquet \
                --date {{ ds }}
            echo "Processing complete"
        """,
    )

    # STEP 4: Archive the original file
    archive_file = BashOperator(
        task_id="archive_original",
        bash_command="""
            mkdir -p /data/archive/{{ ds }}
            mv /data/incoming/vendor_orders_{{ ds_nodash }}.csv \
               /data/archive/{{ ds }}/vendor_orders_{{ ds_nodash }}.csv
            echo "Archived to /data/archive/{{ ds }}/"
        """,
    )

    wait_for_vendor_csv >> validate_file >> process_file >> archive_file
```

---

## Example 2: Wait for a File with Wildcard Pattern

Sometimes you don't know the exact filename, only the pattern. Use glob wildcards.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.filesystem import FileSensor
from airflow.operators.python import PythonOperator

with DAG(
    dag_id="filesensor_wildcard_pattern",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 8 * * 1",   # Every Monday at 8am
    catchup=False,
    tags=["sensor", "file", "glob", "example"],
) as dag:

    # Wait for ANY file matching the pattern
    # Useful when vendor sends files with version numbers or random suffixes
    wait_for_any_report = FileSensor(
        task_id="wait_for_weekly_report",
        filepath="/data/reports/weekly/{{ ds_nodash }}_report_*.xlsx",
        # Matches: 20240115_report_v1.xlsx, 20240115_report_final.xlsx, etc.
        fs_conn_id="fs_default",
        poke_interval=300,         # Check every 5 minutes (less urgent)
        timeout=8 * 60 * 60,       # Wait up to 8 hours
        mode="reschedule",
    )

    # Wait for a directory to appear (sensor can check dirs too)
    wait_for_data_directory = FileSensor(
        task_id="wait_for_data_directory",
        filepath="/data/batches/{{ ds }}/",   # Trailing slash = directory
        fs_conn_id="fs_default",
        poke_interval=120,
        timeout=3600,
        mode="reschedule",
    )

    # After wildcard match, find and process all matching files
    def find_and_process_reports(**context):
        import glob
        import os

        date_nodash = context["ds_nodash"]
        pattern = f"/data/reports/weekly/{date_nodash}_report_*.xlsx"

        # Find all matching files
        matched_files = glob.glob(pattern)
        print(f"Found {len(matched_files)} matching files:")
        for f in matched_files:
            print(f"  - {f} ({os.path.getsize(f) / 1024:.1f} KB)")

        if not matched_files:
            raise FileNotFoundError(f"No files found matching: {pattern}")

        # Sort by modification time — process newest first
        matched_files.sort(key=os.path.getmtime, reverse=True)
        latest_file = matched_files[0]

        print(f"Processing latest file: {latest_file}")
        # ... actual processing logic here

        return {"file": latest_file, "count": len(matched_files)}

    process_reports = PythonOperator(
        task_id="find_and_process_weekly_reports",
        python_callable=find_and_process_reports,
    )

    # Wait for multiple different files (run sensors in parallel)
    wait_for_sales_data = FileSensor(
        task_id="wait_for_sales_data",
        filepath="/data/incoming/sales_{{ ds_nodash }}.csv",
        poke_interval=60,
        timeout=7200,
        mode="reschedule",
    )

    wait_for_returns_data = FileSensor(
        task_id="wait_for_returns_data",
        filepath="/data/incoming/returns_{{ ds_nodash }}.csv",
        poke_interval=60,
        timeout=7200,
        mode="reschedule",
        soft_fail=True,   # Returns data is optional — skip if not received
    )

    def merge_available_files(**context):
        """Process whatever files arrived — returns might be missing (soft_fail)."""
        import os
        date_nodash = context["ds_nodash"]

        sales_file = f"/data/incoming/sales_{date_nodash}.csv"
        returns_file = f"/data/incoming/returns_{date_nodash}.csv"

        files_to_process = []

        if os.path.exists(sales_file):
            files_to_process.append(("sales", sales_file))
            print(f"Sales file found: {sales_file}")
        else:
            print("No sales file — this should not happen (sensor would have failed)")

        if os.path.exists(returns_file):
            files_to_process.append(("returns", returns_file))
            print(f"Returns file found: {returns_file}")
        else:
            print("Returns file not found — processing sales only")

        print(f"Processing {len(files_to_process)} file(s)")
        # ... merge and process

    merge_files = PythonOperator(
        task_id="merge_available_files",
        python_callable=merge_available_files,
        trigger_rule="none_failed",   # Run even if returns sensor was skipped
    )

    # Pipeline 1: weekly reports
    wait_for_any_report >> process_reports

    # Pipeline 2: daily data with optional returns
    [wait_for_sales_data, wait_for_returns_data] >> merge_files
```

**What to notice:**
- Glob patterns like `*` work inside `filepath` — FileSensor uses Python's `glob` module under the hood
- `soft_fail=True` on the returns sensor means a missing returns file causes a **skip**, not a failure
- `trigger_rule="none_failed"` on `merge_files` allows it to run even when the returns sensor was skipped
- Multiple file sensors can run in parallel using the `[sensor_1, sensor_2] >> next_task` pattern
- In the Python function, use `glob.glob()` to find the actual matched files after the sensor confirms at least one exists
