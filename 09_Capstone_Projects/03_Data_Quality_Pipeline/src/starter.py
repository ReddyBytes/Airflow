"""
data_quality_pipeline_starter.py
==================================
Project 03 — Data Quality Gate Pipeline (Intermediate) — STARTER FILE

Fill in every section marked TODO. Use the hints in 03_GUIDE.md when stuck.

Required:
    pip install apache-airflow-providers-postgres \
                great-expectations \
                apache-airflow-providers-great-expectations

    Airflow connections:
        postgres_staging   : Postgres staging DB
        postgres_warehouse : Postgres warehouse DB

    GX resources (create with scripts/create_orders_suite.py first):
        Expectation suite : orders_quality_suite
        Checkpoint        : orders_checkpoint
        Data Context      : /opt/airflow/great_expectations
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.email import EmailOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

# ── Constants ─────────────────────────────────────────────────────────────────
GX_ROOT = "/opt/airflow/great_expectations"
STAGING_CONN = "postgres_staging"
WAREHOUSE_CONN = "postgres_warehouse"
ALERT_EMAIL = "data-team@company.com"

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ALERT_EMAIL,
}

# ── Callables ─────────────────────────────────────────────────────────────────

def check_staging_data(**context) -> None:
    """
    TODO:
    1. Create a PostgresHook for STAGING_CONN
    2. Query: SELECT COUNT(*) FROM staging.orders WHERE order_date = <ds>
    3. If count == 0, raise ValueError with a clear message
    4. Push count to XCom with key "staging_row_count"
    """
    # TODO: implement this function
    pass


def branch_on_validation_result(**context) -> str:
    """
    TODO:
    1. Pull the GX result from XCom (task_ids="validate_data")
       — use xcom_pull(task_ids="validate_data") for the return_value
    2. If result is None, treat as failure — return "build_failure_report"
    3. Read result.get("success", False)
    4. Return "load_to_warehouse" on True, "build_failure_report" on False
    """
    # TODO: implement this function
    pass


def load_validated_rows(**context) -> None:
    """
    TODO:
    1. Create a PostgresHook for WAREHOUSE_CONN
    2. INSERT from staging.orders to warehouse.orders
       - Filter: WHERE order_date = ds AND customer_id IS NOT NULL AND amount >= 0.01
       - Use ON CONFLICT (order_id) DO UPDATE for idempotency
    3. Query the warehouse row count for ds and push to XCom
    """
    # TODO: implement this function
    pass


def build_failure_report(**context) -> str:
    """
    TODO:
    1. Pull the GX result from XCom (task_ids="validate_data")
    2. Extract result.get("statistics", {}) for counts
    3. Extract failed expectations: [r for r in result["results"] if not r["success"]]
    4. Build a plain-text report string listing:
       - date, evaluated count, failed count
       - each failing expectation type + column
       - action required message
    5. Push the report string to XCom with key "failure_report"
    6. Return the report string
    """
    # TODO: implement this function
    pass


# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="data_quality_pipeline",
    description="Postgres staging → GX validation → warehouse load or alert",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["intermediate", "data-quality", "great-expectations"],
) as dag:

    # ── Task 1: Confirm staging data exists ───────────────────────────────────
    check_staging = PythonOperator(
        task_id="check_staging",
        python_callable=check_staging_data,
    )

    # ── Task 2: Run GX validation ─────────────────────────────────────────────
    # TODO: Create a GreatExpectationsOperator with:
    #   - checkpoint_name="orders_checkpoint"
    #   - data_context_root_dir=GX_ROOT
    #   - fail_task_on_validation_failure=False  (why is this critical?)
    #   - return_json_dict=True                  (what does this do?)
    validate = GreatExpectationsOperator(
        task_id="validate_data",
        # TODO: fill in the parameters
    )

    # ── Task 3: Branch on result ──────────────────────────────────────────────
    branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=branch_on_validation_result,
    )

    # ── Task 4a: Load to warehouse ────────────────────────────────────────────
    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_validated_rows,
    )

    # ── Task 4b: Build failure report ─────────────────────────────────────────
    build_report = PythonOperator(
        task_id="build_failure_report",
        python_callable=build_failure_report,
    )

    # ── Task 4c: Send email alert ─────────────────────────────────────────────
    # TODO: Create an EmailOperator that:
    #   - sends to ALERT_EMAIL
    #   - subject includes {{ ds }}
    #   - html_content uses Jinja to pull "failure_report" from XCom
    alert = EmailOperator(
        task_id="send_failure_alert",
        to=ALERT_EMAIL,
        subject="[AIRFLOW] Data Quality FAILED — {{ ds }}",
        html_content="""
        <!-- TODO: include the failure_report from XCom here -->
        """,
    )

    # ── Task 5: Pipeline complete (convergence) ───────────────────────────────
    # TODO: set trigger_rule="none_failed_min_one_success"
    done = EmptyOperator(
        task_id="pipeline_complete",
        # TODO: add trigger_rule here
    )

    # ── Task dependencies ─────────────────────────────────────────────────────
    # TODO: wire the tasks.
    # The pattern:
    #   check_staging >> validate >> branch
    #   branch >> load >> done
    #   branch >> build_report >> alert >> done
