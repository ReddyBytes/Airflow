# PythonOperator — Code Examples

## Example 1: Simple Python Callable

The most basic usage — a function with no arguments, no context needed.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator


# --- Define functions outside the DAG ---

def print_hello():
    """A simple function that logs a message."""
    print("Hello from PythonOperator!")
    print(f"Python is running inside Airflow.")


def check_system_status():
    """Check some basic system status."""
    import platform
    import os

    print(f"Python version: {platform.python_version()}")
    print(f"Operating system: {platform.system()}")
    print(f"Current user: {os.environ.get('USER', 'unknown')}")
    print(f"Working directory: {os.getcwd()}")


def calculate_stats():
    """Do some computation and return a result."""
    numbers = [10, 23, 45, 12, 67, 89, 34, 56]

    total = sum(numbers)
    average = total / len(numbers)
    maximum = max(numbers)
    minimum = min(numbers)

    print(f"Total: {total}")
    print(f"Average: {average:.2f}")
    print(f"Max: {maximum}, Min: {minimum}")

    # Return value is automatically pushed to XCom
    return {
        "total": total,
        "average": average,
        "max": maximum,
        "min": minimum,
    }


# --- Define the DAG ---

with DAG(
    dag_id="python_simple_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["python", "example"],
) as dag:

    greet = PythonOperator(
        task_id="print_greeting",
        python_callable=print_hello,
    )

    check_system = PythonOperator(
        task_id="check_system",
        python_callable=check_system_status,
    )

    compute_stats = PythonOperator(
        task_id="calculate_stats",
        python_callable=calculate_stats,
    )

    greet >> check_system >> compute_stats
```

---

## Example 2: Python Callable with op_kwargs

Pass parameters to your function using `op_kwargs`. Works with Jinja templates too.

```python
from datetime import datetime, timedelta
import json
import os
from airflow import DAG
from airflow.operators.python import PythonOperator


def extract_data(source_url: str, output_dir: str, date: str):
    """
    Extract data from an API for a specific date.

    Args:
        source_url: The API endpoint to call
        output_dir: Directory to save the downloaded file
        date: The date to extract data for (YYYY-MM-DD)
    """
    import requests

    print(f"Extracting data for date: {date}")
    print(f"Source: {source_url}")

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    response = requests.get(
        source_url,
        params={"date": date},
        timeout=60,
    )
    response.raise_for_status()

    output_file = os.path.join(output_dir, f"data_{date}.json")
    with open(output_file, "w") as f:
        json.dump(response.json(), f, indent=2)

    record_count = len(response.json())
    print(f"Saved {record_count} records to {output_file}")
    return record_count  # XCom: downstream tasks can check how many records


def transform_data(input_dir: str, output_dir: str, date: str, drop_nulls: bool = True):
    """
    Transform raw data: clean, filter, and reshape.

    Args:
        input_dir: Directory with raw data files
        output_dir: Directory to write processed data
        date: The date being processed
        drop_nulls: Whether to drop records with null values
    """
    print(f"Transforming data for {date} (drop_nulls={drop_nulls})")

    input_file = os.path.join(input_dir, f"data_{date}.json")

    with open(input_file) as f:
        records = json.load(f)

    print(f"Loaded {len(records)} raw records")

    # Apply transformations
    if drop_nulls:
        records = [r for r in records if all(v is not None for v in r.values())]
        print(f"After dropping nulls: {len(records)} records")

    # Flatten nested fields (example)
    processed = []
    for r in records:
        flat = {
            "id": r.get("id"),
            "name": r.get("name", "").strip().lower(),
            "amount": float(r.get("amount", 0)),
            "processed_date": date,
        }
        processed.append(flat)

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"processed_{date}.json")

    with open(output_file, "w") as f:
        json.dump(processed, f, indent=2)

    print(f"Wrote {len(processed)} processed records to {output_file}")
    return len(processed)


def load_summary(date: str, raw_dir: str, processed_dir: str):
    """Print a summary of what was extracted and transformed."""
    raw_file = os.path.join(raw_dir, f"data_{date}.json")
    processed_file = os.path.join(processed_dir, f"processed_{date}.json")

    raw_count = len(json.load(open(raw_file)))
    processed_count = len(json.load(open(processed_file)))
    dropped = raw_count - processed_count

    print(f"=== Pipeline Summary for {date} ===")
    print(f"Raw records:       {raw_count}")
    print(f"Processed records: {processed_count}")
    print(f"Dropped (nulls):   {dropped}")
    print(f"Retention rate:    {(processed_count/raw_count)*100:.1f}%")


with DAG(
    dag_id="python_kwargs_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=3)},
    tags=["python", "kwargs", "example"],
) as dag:

    extract = PythonOperator(
        task_id="extract_data",
        python_callable=extract_data,
        op_kwargs={
            "source_url": "https://api.example.com/records",
            "output_dir": "/tmp/pipeline/raw",
            "date": "{{ ds }}",             # Jinja: renders to "2024-01-15" etc.
        },
    )

    transform = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
        op_kwargs={
            "input_dir": "/tmp/pipeline/raw",
            "output_dir": "/tmp/pipeline/processed",
            "date": "{{ ds }}",
            "drop_nulls": True,
        },
    )

    summarize = PythonOperator(
        task_id="print_summary",
        python_callable=load_summary,
        op_kwargs={
            "date": "{{ ds }}",
            "raw_dir": "/tmp/pipeline/raw",
            "processed_dir": "/tmp/pipeline/processed",
        },
    )

    extract >> transform >> summarize
```

---

## Example 3: Function That Pulls and Pushes XCom Values

Demonstrate the full XCom round-trip: pushing from one task and pulling in another.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator


# Task 1: Extract — pushes multiple XCom values
def extract_from_api(**context):
    """
    Simulates extracting data from an API.
    Returns a dict — Airflow stores this in XCom as 'return_value'.
    Also manually pushes a separate XCom key.
    """
    ti = context["ti"]
    execution_date = context["ds"]

    print(f"Extracting data for {execution_date}")

    # Simulate API response
    data = {
        "records": [
            {"id": 1, "value": 100, "status": "active"},
            {"id": 2, "value": 200, "status": "inactive"},
            {"id": 3, "value": 150, "status": "active"},
        ],
        "total_count": 3,
        "api_version": "v2",
    }

    # Push a separate XCom key manually (not just return_value)
    ti.xcom_push(key="record_count", value=len(data["records"]))
    ti.xcom_push(key="api_version", value=data["api_version"])

    print(f"Extracted {len(data['records'])} records")

    # The returned dict is pushed as 'return_value' XCom key
    return data


# Task 2: Validate — pulls and checks the extracted data
def validate_data(**context):
    """
    Pulls XCom from the extract task and validates the data.
    """
    ti = context["ti"]

    # Pull the full returned dict (key='return_value' is default)
    extracted = ti.xcom_pull(task_ids="extract_from_api")

    # Pull specific manually-pushed XCom keys
    record_count = ti.xcom_pull(task_ids="extract_from_api", key="record_count")
    api_version = ti.xcom_pull(task_ids="extract_from_api", key="api_version")

    print(f"Received {record_count} records (API version: {api_version})")
    print(f"Full data: {extracted}")

    # Validate
    if record_count == 0:
        raise ValueError("No records extracted — pipeline cannot continue")

    active_records = [r for r in extracted["records"] if r["status"] == "active"]
    inactive_records = [r for r in extracted["records"] if r["status"] == "inactive"]

    print(f"Active: {len(active_records)}, Inactive: {len(inactive_records)}")

    # Push validation summary for downstream tasks
    validation_result = {
        "is_valid": True,
        "active_count": len(active_records),
        "inactive_count": len(inactive_records),
        "total": record_count,
    }

    # Return value becomes next task's xcom_pull() result
    return validation_result


# Task 3: Load — pulls from both upstream tasks
def load_to_database(**context):
    """
    Pulls data from both upstream tasks and simulates loading to a DB.
    """
    ti = context["ti"]
    execution_date = context["ds"]

    # Pull from extract task
    raw_data = ti.xcom_pull(task_ids="extract_from_api")
    record_count = ti.xcom_pull(task_ids="extract_from_api", key="record_count")

    # Pull from validate task
    validation = ti.xcom_pull(task_ids="validate_data")

    print(f"Loading data for {execution_date}")
    print(f"Total records: {record_count}")
    print(f"Validation result: {validation}")

    if not validation["is_valid"]:
        raise ValueError("Validation failed — not loading to DB")

    # Simulate DB insert
    for record in raw_data["records"]:
        print(f"  Inserting record {record['id']} (status={record['status']})")

    rows_inserted = len(raw_data["records"])
    print(f"Successfully inserted {rows_inserted} rows")

    return {"rows_inserted": rows_inserted, "date": execution_date}


# Task 4: Report — summarizes the entire pipeline run
def send_pipeline_report(**context):
    """Final task: pulls results from all tasks and prints a summary."""
    ti = context["ti"]

    load_result = ti.xcom_pull(task_ids="load_to_database")
    validation = ti.xcom_pull(task_ids="validate_data")
    api_version = ti.xcom_pull(task_ids="extract_from_api", key="api_version")

    print("=" * 40)
    print("PIPELINE SUMMARY")
    print("=" * 40)
    print(f"Date:            {load_result['date']}")
    print(f"API Version:     {api_version}")
    print(f"Active records:  {validation['active_count']}")
    print(f"Rows inserted:   {load_result['rows_inserted']}")
    print(f"Status:          SUCCESS")
    print("=" * 40)


with DAG(
    dag_id="python_xcom_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["python", "xcom", "example"],
) as dag:

    extract = PythonOperator(
        task_id="extract_from_api",
        python_callable=extract_from_api,
    )

    validate = PythonOperator(
        task_id="validate_data",
        python_callable=validate_data,
    )

    load = PythonOperator(
        task_id="load_to_database",
        python_callable=load_to_database,
    )

    report = PythonOperator(
        task_id="send_pipeline_report",
        python_callable=send_pipeline_report,
    )

    extract >> validate >> load >> report
```

**What to notice:**
- `return value` → automatically stored in XCom as key `return_value`
- `ti.xcom_push(key="my_key", value=...)` → manually push extra XCom values
- `ti.xcom_pull(task_ids="upstream_task")` → pulls `return_value` by default
- `ti.xcom_pull(task_ids="upstream_task", key="my_key")` → pulls a specific key
- The `**context` pattern captures all context kwargs including `ti`, `ds`, `dag`, etc.
