# 09 — XComs: Code Examples

## Example 1 — Basic Push/Pull with ti.xcom_push / xcom_pull

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def find_latest_file(ti, **context):
    # Simulate discovering the latest file
    filename = "sales_2024_03_15_v7.csv"
    row_count = 42_000

    # Push multiple keys from one task
    ti.xcom_push(key="filename", value=filename)
    ti.xcom_push(key="row_count", value=row_count)
    print(f"Pushed filename={filename}, row_count={row_count}")

def process_file(ti, **context):
    # Pull each key by name
    filename  = ti.xcom_pull(task_ids="find_latest_file", key="filename")
    row_count = ti.xcom_pull(task_ids="find_latest_file", key="row_count")

    print(f"Processing {filename} ({row_count:,} rows)")

with DAG(
    dag_id="xcom_push_pull",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    t1 = PythonOperator(task_id="find_latest_file", python_callable=find_latest_file)
    t2 = PythonOperator(task_id="process_file",     python_callable=process_file)

    t1 >> t2
```

---

## Example 2 — Automatic Push via Return Value

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def extract():
    # Return value is automatically pushed as key="return_value"
    return {"filename": "sales_2024_03_15_v7.csv", "source": "s3"}

def transform(ti, **context):
    # Pull key="return_value" (default — no key argument needed)
    metadata = ti.xcom_pull(task_ids="extract")
    filename = metadata["filename"]

    # This task's return value is also auto-pushed
    return {"filename": filename, "rows_processed": 42_000, "status": "ok"}

def load(ti, **context):
    summary = ti.xcom_pull(task_ids="transform")
    print(f"Loaded {summary['rows_processed']} rows from {summary['filename']}")
    print(f"Status: {summary['status']}")

with DAG(
    dag_id="xcom_return_value",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    t1 = PythonOperator(task_id="extract",   python_callable=extract)
    t2 = PythonOperator(task_id="transform", python_callable=transform)
    t3 = PythonOperator(task_id="load",      python_callable=load)

    t1 >> t2 >> t3
```

---

## Example 3 — TaskFlow API with @task Decorator

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id="xcom_taskflow",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
)
def xcom_taskflow_dag():

    @task
    def extract() -> dict:
        # Return value is automatically an XCom — no ti.xcom_push needed
        return {"filename": "sales_2024_03_15_v7.csv", "rows": 42_000}

    @task
    def validate(metadata: dict) -> bool:
        # "metadata" is automatically pulled from the "extract" XCom
        print(f"Validating {metadata['filename']} ({metadata['rows']} rows)")
        is_valid = metadata["rows"] > 0
        return is_valid

    @task
    def load(metadata: dict, is_valid: bool):
        # Both upstream XComs are injected as arguments
        if not is_valid:
            raise ValueError("Validation failed — skipping load")
        print(f"Loading {metadata['filename']}")

    # Airflow infers the DAG structure from the function call chain
    meta = extract()
    valid = validate(meta)
    load(meta, valid)

xcom_taskflow_dag()
```

---

## Example 4 — Pull XCom from a Different task_id / Specific DAG Run

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def push_job_id(ti, **context):
    job_id = "batch-job-20240315-001"
    ti.xcom_push(key="job_id", value=job_id)

def check_job_status(ti, **context):
    # Pull from a specific task in the current DAG run
    job_id = ti.xcom_pull(task_ids="submit_job", key="job_id")
    print(f"Checking status for job: {job_id}")

def cross_dag_example(ti, **context):
    # Pull XCom from a DIFFERENT DAG (use sparingly — creates hidden coupling)
    upstream_result = ti.xcom_pull(
        dag_id="upstream_pipeline_dag",   # another DAG
        task_ids="final_task",
        key="output_path",
        # run_id defaults to current run's run_id;
        # pass an explicit run_id to reach a different run
    )
    print(f"Upstream wrote output to: {upstream_result}")

def pull_from_multiple_tasks(ti, **context):
    # Pull the same key from multiple tasks — returns a list
    statuses = ti.xcom_pull(
        task_ids=["validate_schema", "validate_counts", "validate_nulls"],
        key="status",
    )
    # statuses = ["ok", "ok", "warning"]
    all_ok = all(s == "ok" for s in statuses)
    print(f"All checks passed: {all_ok}")

with DAG(
    dag_id="xcom_advanced",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    submit   = PythonOperator(task_id="submit_job",           python_callable=push_job_id)
    check    = PythonOperator(task_id="check_job_status",     python_callable=check_job_status)
    multi    = PythonOperator(task_id="pull_multiple",        python_callable=pull_from_multiple_tasks)

    submit >> check >> multi
```
