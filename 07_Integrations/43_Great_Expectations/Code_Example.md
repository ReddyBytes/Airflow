# Airflow + Great Expectations — Code Examples

Working DAG patterns for data quality validation with Great Expectations.

---

## 1. Basic GreatExpectationsOperator in a DAG

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

with DAG(
    dag_id="orders_with_quality_check",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["data-quality", "great-expectations"],
) as dag:

    # Step 1: Extract / stage the data
    stage_orders = PostgresOperator(
        task_id="stage_orders",
        postgres_conn_id="warehouse",
        sql="""
            CREATE TABLE IF NOT EXISTS staging.orders_{{ ds_nodash }} AS
            SELECT * FROM raw.orders
            WHERE DATE(created_at) = '{{ ds }}'
        """,
    )

    # Step 2: Validate staged data against expectation suite
    validate_orders = GreatExpectationsOperator(
        task_id="validate_orders",
        checkpoint_name="orders_daily_checkpoint",
        data_context_root_dir="/opt/airflow/great_expectations",
        checkpoint_kwargs={
            "batch_request": {
                "datasource_name": "postgres_source",
                "data_connector_name": "default_inferred",
                "data_asset_name": "staging.orders_{{ ds_nodash }}",
            }
        },
        fail_task_on_validation_failure=True,
    )

    # Step 3: Load to production table (only runs if validation passes)
    load_orders = PostgresOperator(
        task_id="load_orders",
        postgres_conn_id="warehouse",
        sql="""
            INSERT INTO production.orders
            SELECT * FROM staging.orders_{{ ds_nodash }}
            ON CONFLICT (order_id) DO UPDATE
                SET amount = EXCLUDED.amount,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
        """,
    )

    stage_orders >> validate_orders >> load_orders
```

---

## 2. Custom Expectation Suite (Programmatic)

```python
# scripts/create_orders_suite.py
# Run once to create the suite file.
# Commit great_expectations/expectations/orders_suite.json to version control.

import great_expectations as gx

context = gx.get_context(context_root_dir="/opt/airflow/great_expectations")

# Remove and recreate to keep idempotent
try:
    context.delete_expectation_suite("orders_suite")
except Exception:
    pass

suite = context.add_expectation_suite("orders_suite")

# Get a validator pointing at our Postgres table
batch_request = {
    "datasource_name": "postgres_source",
    "data_connector_name": "default_inferred",
    "data_asset_name": "staging.orders_sample",
}
validator = context.get_validator(
    batch_request=batch_request,
    expectation_suite_name="orders_suite",
)

# Table-level expectations
validator.expect_table_row_count_to_be_between(min_value=1, max_value=5_000_000)
validator.expect_table_column_count_to_equal(7)

# Column-level expectations
validator.expect_column_values_to_not_be_null("order_id")
validator.expect_column_values_to_be_unique("order_id")
validator.expect_column_values_to_not_be_null("customer_id")
validator.expect_column_values_to_be_between("amount", min_value=0.01)
validator.expect_column_values_to_be_in_set(
    "currency", ["USD", "EUR", "GBP", "JPY"]
)
validator.expect_column_values_to_be_in_set(
    "status", ["pending", "shipped", "delivered", "cancelled", "refunded"]
)
validator.expect_column_values_to_match_regex(
    "order_id", r"^ORD-[0-9]{8}$"
)
validator.expect_column_values_to_be_between(
    "created_at",
    min_value="2020-01-01",
    max_value="2030-12-31",
    parse_strings_as_datetimes=True,
)

validator.save_expectation_suite(discard_failed_expectations=False)
print("Suite saved.")
```

---

## 3. Handling Validation Failure Gracefully with BranchPythonOperator

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.operators.email import EmailOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

def decide_next_step(**context):
    """Branch based on GX validation result XCom."""
    result = context["ti"].xcom_pull(task_ids="validate_data")
    if result and result.get("success"):
        return "load_to_warehouse"
    else:
        # Log which expectations failed
        for res in result.get("results", []):
            if not res["success"]:
                print(f"FAILED: {res['expectation_config']['expectation_type']} "
                      f"on column {res['expectation_config']['kwargs'].get('column', 'N/A')}")
        return "send_failure_alert"

def log_validation_details(**context):
    result = context["ti"].xcom_pull(task_ids="validate_data")
    stats = result.get("statistics", {})
    print(f"Evaluated: {stats.get('evaluated_expectations')}")
    print(f"Successful: {stats.get('successful_expectations')}")
    print(f"Failed: {stats.get('unsuccessful_expectations')}")

with DAG(
    dag_id="quality_gate_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    extract = PythonOperator(
        task_id="extract_data",
        python_callable=lambda: print("Extracting..."),
    )

    validate = GreatExpectationsOperator(
        task_id="validate_data",
        checkpoint_name="orders_checkpoint",
        data_context_root_dir="/opt/airflow/great_expectations",
        fail_task_on_validation_failure=False,   # don't fail; let us branch
        return_json_dict=True,                   # push result to XCom
    )

    branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=decide_next_step,
    )

    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=lambda: print("Loading clean data..."),
    )

    alert = EmailOperator(
        task_id="send_failure_alert",
        to="data-team@company.com",
        subject="Data Quality Failure — {{ ds }}",
        html_content="""
            <h3>Data quality validation failed for {{ ds }}</h3>
            <p>Check the Airflow logs and GX Data Docs for details.</p>
        """,
    )

    extract >> validate >> branch >> [load, alert]
```

---

## 4. Generating Data Docs After Validation

```python
from datetime import datetime
from airflow.operators.python import PythonOperator
from airflow.sdk import DAG
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

def build_and_publish_data_docs():
    import great_expectations as gx
    import boto3

    context = gx.get_context(context_root_dir="/opt/airflow/great_expectations")
    context.build_data_docs()

    # Upload to S3 for sharing with stakeholders
    s3 = boto3.client("s3")
    docs_path = "/opt/airflow/great_expectations/uncommitted/data_docs/local_site/"
    import os
    for root, _, files in os.walk(docs_path):
        for file in files:
            local_path = os.path.join(root, file)
            s3_key = "data-docs/" + local_path.replace(docs_path, "")
            s3.upload_file(local_path, "my-data-docs-bucket", s3_key,
                           ExtraArgs={"ContentType": "text/html"})
    print("Data Docs published to s3://my-data-docs-bucket/data-docs/")

with DAG(
    dag_id="validation_with_docs",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    validate = GreatExpectationsOperator(
        task_id="validate",
        checkpoint_name="orders_checkpoint",
        data_context_root_dir="/opt/airflow/great_expectations",
        fail_task_on_validation_failure=True,
    )

    publish_docs = PythonOperator(
        task_id="publish_data_docs",
        python_callable=build_and_publish_data_docs,
        trigger_rule="all_done",    # publish docs even on failure (shows what failed)
    )

    validate >> publish_docs
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Spark** | [42_Spark_Integration](../42_Spark_Integration/Theory.md) |
| **Next: KPO Deep Dive** | [44_KubernetesPodOperator_Deep_Dive](../44_KubernetesPodOperator_Deep_Dive/Theory.md) |
