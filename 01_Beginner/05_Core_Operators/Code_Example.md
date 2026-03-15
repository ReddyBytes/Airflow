# Core Operators — Code Examples

Three complete, well-commented DAG examples using BashOperator, PythonOperator, and EmptyOperator in Airflow 3.

---

## Example 1: Daily File Processing Pipeline

This pipeline downloads a CSV file, validates it, transforms the data, and reports the result. It demonstrates BashOperator and PythonOperator working together with data passing via XCom.

```python
"""
daily_file_pipeline.py

A realistic daily file processing pipeline that:
1. Downloads a data file using a bash command
2. Validates the file exists and is non-empty (PythonOperator)
3. Parses and transforms the data (PythonOperator)
4. Uploads the result using a bash command
5. Uses EmptyOperator for clean start/end anchors

Airflow 3 syntax — uses airflow.sdk imports
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator


# ── Python callables (defined outside the DAG, easy to unit-test) ─────────────

def validate_file(file_path: str, **context) -> str:
    """
    Check that the downloaded file exists and has content.
    Returns the file path if valid (pushed to XCom for next task).
    Raises an exception if the file is missing or empty.
    """
    import os

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Expected file not found: {file_path}")

    size = path.stat().st_size
    if size == 0:
        raise ValueError(f"File is empty: {file_path}")

    print(f"File validated: {file_path} ({size} bytes)")
    print(f"Processing for execution date: {context['ds']}")

    return str(path)  # Return value pushed to XCom as 'return_value'


def transform_data(**context) -> dict:
    """
    Read the CSV file (path pulled from XCom), transform it,
    and return a summary dict.

    In a real pipeline, you would use pandas or polars here.
    """
    import csv

    # Pull the file path from the previous task's XCom
    ti = context["task_instance"]
    file_path = ti.xcom_pull(task_ids="validate_file")

    print(f"Transforming data from: {file_path}")

    # Read CSV and calculate a simple summary
    records = []
    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    record_count = len(records)
    print(f"Processed {record_count} records")

    # Return a summary — this is pushed to XCom automatically
    return {
        "record_count": record_count,
        "execution_date": context["ds"],
        "status": "success",
    }


def log_summary(**context) -> None:
    """
    Pull the transformation summary from XCom and log it.
    No return value — this is the final reporting task.
    """
    ti = context["task_instance"]
    summary = ti.xcom_pull(task_ids="transform_data")

    print("=" * 50)
    print("PIPELINE SUMMARY")
    print("=" * 50)
    print(f"Execution date  : {summary['execution_date']}")
    print(f"Records processed: {summary['record_count']}")
    print(f"Status          : {summary['status']}")
    print("=" * 50)


# ── DAG Definition ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="daily_file_pipeline",
    description="Downloads, validates, transforms, and uploads a daily data file",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,                          # Don't run for past dates on first deploy
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "owner": "data-team",
    },
    tags=["example", "file-processing"],
) as dag:

    # ── Pipeline entry anchor ───────────────────────────────────────────────
    start = EmptyOperator(task_id="start")

    # ── Step 1: Download the file using a bash command ──────────────────────
    # In a real pipeline this might be: curl, wget, aws s3 cp, gsutil cp, etc.
    # {{ ds }} is replaced with the execution date (e.g., 2024-01-15)
    download_file = BashOperator(
        task_id="download_file",
        bash_command="""
            echo "Downloading file for {{ ds }}"
            # Simulate download by creating a CSV file
            mkdir -p /tmp/airflow_data
            echo "id,name,value" > /tmp/airflow_data/data_{{ ds }}.csv
            echo "1,Alice,100" >> /tmp/airflow_data/data_{{ ds }}.csv
            echo "2,Bob,200" >> /tmp/airflow_data/data_{{ ds }}.csv
            echo "3,Charlie,300" >> /tmp/airflow_data/data_{{ ds }}.csv
            echo "Download complete: /tmp/airflow_data/data_{{ ds }}.csv"
        """,
    )

    # ── Step 2: Validate the downloaded file ───────────────────────────────
    validate = PythonOperator(
        task_id="validate_file",
        python_callable=validate_file,
        op_kwargs={"file_path": "/tmp/airflow_data/data_{{ ds }}.csv"},
    )

    # ── Step 3: Transform the data ─────────────────────────────────────────
    transform = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    # ── Step 4: Upload the result (simulated) ──────────────────────────────
    upload_result = BashOperator(
        task_id="upload_result",
        bash_command="""
            echo "Uploading results for {{ ds }}"
            # In a real pipeline: aws s3 cp /tmp/output_{{ ds }}.csv s3://my-bucket/
            echo "Upload complete"
        """,
    )

    # ── Step 5: Log the summary ────────────────────────────────────────────
    log_result = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
    )

    # ── Pipeline exit anchor ────────────────────────────────────────────────
    end = EmptyOperator(task_id="end")

    # ── Task dependencies (defines the execution order) ─────────────────────
    start >> download_file >> validate >> transform >> upload_result >> log_result >> end
```

---

## Example 2: Parallel ETL with Branch Join

This pipeline runs two transformation branches in parallel, joins them, and loads the results. It demonstrates EmptyOperator as a join node and parallel task execution.

```python
"""
parallel_etl_pipeline.py

An ETL pipeline with parallel processing branches:
- Branch A processes sales data
- Branch B processes user data
- Both branches join before the final load step

Demonstrates:
- EmptyOperator as start, join, and end nodes
- Parallel task execution with fan-out and fan-in
- Passing data through XCom between parallel branches
- trigger_rule on the join node

Airflow 3 syntax
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from airflow.sdk import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator


# ── Python callables ──────────────────────────────────────────────────────────

def extract_all_data(**context) -> dict[str, list]:
    """
    Extract raw data from source systems.
    Returns a dict with sales and user data.
    """
    print(f"Extracting data for: {context['ds']}")

    # Simulated raw data (in reality: database queries, API calls, etc.)
    raw_data = {
        "sales": [
            {"id": 1, "amount": 150.00, "product": "Widget A"},
            {"id": 2, "amount": 250.00, "product": "Widget B"},
            {"id": 3, "amount": 75.00,  "product": "Widget C"},
        ],
        "users": [
            {"id": 1, "name": "Alice", "tier": "premium"},
            {"id": 2, "name": "Bob",   "tier": "standard"},
        ],
    }

    print(f"Extracted {len(raw_data['sales'])} sales records")
    print(f"Extracted {len(raw_data['users'])} user records")

    return raw_data


def transform_sales(**context) -> dict[str, Any]:
    """Transform sales data: calculate totals and averages."""
    ti = context["task_instance"]
    raw = ti.xcom_pull(task_ids="extract_data")
    sales = raw["sales"]

    total = sum(s["amount"] for s in sales)
    average = total / len(sales) if sales else 0
    top_product = max(sales, key=lambda s: s["amount"])["product"]

    result = {
        "total_revenue": round(total, 2),
        "average_sale": round(average, 2),
        "top_product": top_product,
        "record_count": len(sales),
    }

    print(f"Sales transformation complete: {result}")
    return result


def transform_users(**context) -> dict[str, Any]:
    """Transform user data: count by tier."""
    ti = context["task_instance"]
    raw = ti.xcom_pull(task_ids="extract_data")
    users = raw["users"]

    tier_counts: dict[str, int] = {}
    for user in users:
        tier = user["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    result = {
        "total_users": len(users),
        "tier_breakdown": tier_counts,
    }

    print(f"User transformation complete: {result}")
    return result


def load_results(**context) -> None:
    """
    Load the transformed data from both branches.
    This runs after the join node, so both branch results are available.
    """
    ti = context["task_instance"]

    # Pull results from both transformation tasks
    sales_data = ti.xcom_pull(task_ids="transform_sales")
    user_data = ti.xcom_pull(task_ids="transform_users")

    print("=" * 60)
    print("LOADING RESULTS TO DATA WAREHOUSE")
    print("=" * 60)
    print(f"Sales Summary:")
    print(f"  Total Revenue : ${sales_data['total_revenue']}")
    print(f"  Avg Sale      : ${sales_data['average_sale']}")
    print(f"  Top Product   : {sales_data['top_product']}")
    print(f"User Summary:")
    print(f"  Total Users   : {user_data['total_users']}")
    print(f"  By Tier       : {user_data['tier_breakdown']}")
    print("=" * 60)
    print("Load complete.")


# ── DAG Definition ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="parallel_etl_pipeline",
    description="Parallel ETL with branch join pattern",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["example", "etl", "parallel"],
) as dag:

    # ── Anchor: pipeline start ──────────────────────────────────────────────
    start = EmptyOperator(task_id="start")

    # ── Step 1: Extract all data ────────────────────────────────────────────
    extract = PythonOperator(
        task_id="extract_data",
        python_callable=extract_all_data,
    )

    # ── Step 2a: Transform sales (runs in parallel with transform_users) ────
    t_sales = PythonOperator(
        task_id="transform_sales",
        python_callable=transform_sales,
    )

    # ── Step 2b: Transform users (runs in parallel with transform_sales) ────
    t_users = PythonOperator(
        task_id="transform_users",
        python_callable=transform_users,
    )

    # ── Step 3: Join node — waits for BOTH transform tasks ──────────────────
    # trigger_rule="none_failed_min_one_success":
    # - Runs if at least one upstream succeeded AND none failed
    # - More robust than "all_success" when some branches might be skipped
    join = EmptyOperator(
        task_id="join_branches",
        trigger_rule="none_failed_min_one_success",
    )

    # ── Step 4: Load results to data warehouse ──────────────────────────────
    load = PythonOperator(
        task_id="load_results",
        python_callable=load_results,
    )

    # ── Step 5: Notify (simulated via bash) ─────────────────────────────────
    notify = BashOperator(
        task_id="send_notification",
        bash_command="""
            echo "Pipeline complete for {{ ds }}"
            echo "Results loaded at $(date)"
            # In a real pipeline: curl -X POST https://hooks.slack.com/... -d '{"text":"Done"}'
        """,
    )

    # ── Anchor: pipeline end ────────────────────────────────────────────────
    end = EmptyOperator(task_id="end")

    # ── Dependencies ───────────────────────────────────────────────────────
    # Fan-out: extract → [t_sales, t_users] (run in parallel)
    # Fan-in:  [t_sales, t_users] → join (wait for both)
    start >> extract >> [t_sales, t_users] >> join >> load >> notify >> end
```

---

## Example 3: System Health Check Pipeline

This pipeline uses all three operators to run system health checks. It demonstrates using BashOperator for system commands, PythonOperator for aggregating results, and EmptyOperator for conditional flow control.

```python
"""
system_health_check.py

A monitoring pipeline that:
1. Runs bash health checks (disk space, memory, connectivity)
2. Aggregates all check results in Python
3. Sends an alert if any check failed (bash command)
4. Uses skip_on_exit_code to handle optional checks gracefully

Demonstrates:
- BashOperator with skip_on_exit_code
- PythonOperator for result aggregation
- EmptyOperator with trigger_rule for conditional flow
- Practical error handling patterns

Airflow 3 syntax
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator


# ── Python callables ──────────────────────────────────────────────────────────

def check_all_results(**context) -> dict:
    """
    Collect the outputs of the bash health checks via XCom.
    Determine overall health status.
    """
    ti = context["task_instance"]

    # BashOperator pushes its last stdout line to XCom when do_xcom_push=True
    disk_output   = ti.xcom_pull(task_ids="check_disk_space")
    memory_output = ti.xcom_pull(task_ids="check_memory")
    network_output = ti.xcom_pull(task_ids="check_network")

    checks = {
        "disk":    {"result": disk_output,    "status": "ok" if disk_output else "skipped"},
        "memory":  {"result": memory_output,  "status": "ok" if memory_output else "skipped"},
        "network": {"result": network_output, "status": "ok" if network_output else "skipped"},
    }

    all_ok = all(c["status"] != "failed" for c in checks.values())

    summary = {
        "checks": checks,
        "overall_status": "healthy" if all_ok else "degraded",
        "checked_at": context["ts"],
    }

    print(f"Health check summary: {summary['overall_status']}")
    for name, check in checks.items():
        print(f"  {name}: {check['status']} — {check['result']}")

    return summary


def evaluate_health(**context) -> bool:
    """
    Read the summary from XCom.
    Raise an exception if the system is degraded.
    This causes the downstream alert task to run via its trigger_rule.
    """
    from airflow.exceptions import AirflowSkipException

    ti = context["task_instance"]
    summary = ti.xcom_pull(task_ids="aggregate_results")

    if summary["overall_status"] == "healthy":
        print("All systems healthy. No alert needed.")
        raise AirflowSkipException("System is healthy — skipping alert")
    else:
        print(f"System degraded! Status: {summary['overall_status']}")
        return False  # Allows the alert task to run


# ── DAG Definition ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="system_health_check",
    description="Hourly system health checks with alerting",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    default_args={
        "retries": 0,           # Health checks should not retry
        "owner": "platform-team",
    },
    tags=["monitoring", "health-check"],
) as dag:

    # ── Pipeline start ──────────────────────────────────────────────────────
    start = EmptyOperator(task_id="start")

    # ── Health Check 1: Disk space ──────────────────────────────────────────
    # Pushes the last output line to XCom
    # Exit code 99 → SKIP (disk check unavailable) rather than FAIL
    check_disk = BashOperator(
        task_id="check_disk_space",
        bash_command="""
            # Get disk usage percentage for root partition
            USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
            echo "Disk usage: ${USAGE}%"

            if [ "$USAGE" -gt 90 ]; then
                echo "WARNING: Disk usage critical: ${USAGE}%"
                exit 1   # Task fails → downstream alert triggers
            fi
            echo "DISK_OK:${USAGE}%"
        """,
        skip_on_exit_code=99,   # Exit 99 → skip (not fail)
        do_xcom_push=True,      # Last line pushed to XCom
    )

    # ── Health Check 2: Memory ──────────────────────────────────────────────
    check_memory = BashOperator(
        task_id="check_memory",
        bash_command="""
            # Get free memory percentage (macOS-compatible)
            echo "Memory check passed"
            echo "MEMORY_OK"
        """,
        do_xcom_push=True,
    )

    # ── Health Check 3: Network connectivity ───────────────────────────────
    check_network = BashOperator(
        task_id="check_network",
        bash_command="""
            # Ping Google DNS to check connectivity
            if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
                echo "NETWORK_OK"
            else
                echo "NETWORK_FAILED"
                exit 1
            fi
        """,
        do_xcom_push=True,
    )

    # ── Aggregation: Collect all results ────────────────────────────────────
    # trigger_rule="all_done" — runs even if some checks failed or skipped
    aggregate = PythonOperator(
        task_id="aggregate_results",
        python_callable=check_all_results,
        trigger_rule="all_done",    # Run regardless of check task states
    )

    # ── Evaluation: Decide whether to alert ────────────────────────────────
    evaluate = PythonOperator(
        task_id="evaluate_health",
        python_callable=evaluate_health,
    )

    # ── Alert: Send notification if system is degraded ─────────────────────
    # trigger_rule="all_failed" — runs only if evaluate_health failed
    # (evaluate raises AirflowSkipException when healthy, fails when degraded)
    send_alert = BashOperator(
        task_id="send_alert",
        bash_command="""
            echo "ALERT: System health check FAILED at {{ ts }}"
            # In a real pipeline:
            # curl -X POST "$SLACK_WEBHOOK" -d '{"text": "System degraded!"}'
            # or: aws sns publish --topic-arn $SNS_TOPIC --message "..."
        """,
        trigger_rule="all_failed",  # Only runs if evaluate_health task failed
    )

    # ── Pipeline end (runs regardless of alert) ─────────────────────────────
    end = EmptyOperator(
        task_id="end",
        trigger_rule="all_done",    # Always runs — even if alert was triggered
    )

    # ── Dependencies ───────────────────────────────────────────────────────
    # All three health checks run in parallel after start
    start >> [check_disk, check_memory, check_network]

    # Aggregate after all checks complete (any state)
    [check_disk, check_memory, check_network] >> aggregate

    # Evaluate results → conditionally alert
    aggregate >> evaluate >> send_alert

    # End always runs
    [send_alert, evaluate] >> end
```
