"""
forex_etl_pipeline_starter.py
==============================
Project 01 — Forex ETL Pipeline (Beginner) — STARTER FILE

Fill in every section marked TODO. Run the test commands in 03_GUIDE.md
after each phase to verify your work before moving on.

Prerequisites:
    pip install apache-airflow-providers-http apache-airflow-providers-postgres

    Airflow connections needed:
        forex_api      : HTTP, host=https://v6.exchangerate-api.com
        forex_postgres : Postgres, host=localhost, schema=forex, port=5432

    Environment variable:
        FOREX_API_KEY=your_api_key_here  (free key from exchangerate-api.com)
"""

import json
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.hooks.http import HttpHook
from airflow.sensors.filesystem import FileSensor
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_CURRENCY = "USD"
TARGET_CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY"]
DATA_DIR = "/tmp/forex"
CONFIG_FILE = f"{DATA_DIR}/currencies.json"

# ── Default args applied to all tasks ─────────────────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["data-team@company.com"],
}

# ── DAG definition ─────────────────────────────────────────────────────────────
with DAG(
    dag_id="forex_etl_pipeline",
    description="Daily forex ETL: API → CSV → PostgreSQL → Email",
    start_date=datetime(2024, 1, 1),
    schedule="0 6 * * *",   # TODO: what does this cron mean? (see 02_ARCHITECTURE.md)
    catchup=False,
    default_args=default_args,
    tags=["beginner", "etl", "forex"],
) as dag:

    # ── Task 1: Check the API is alive ─────────────────────────────────────────
    # TODO: Create an HttpSensor that:
    #   - uses conn_id "forex_api"
    #   - polls endpoint "/v6/latest/USD"
    #   - passes {"apikey": os.environ.get("FOREX_API_KEY", "demo")} as request_params
    #   - uses response_check to confirm response.json()["result"] == "success"
    #   - poke_interval=5, timeout=20
    check_api_availability = HttpSensor(
        task_id="check_api_availability",
        # TODO: fill in the parameters
    )

    # ── Task 2: Check the config file exists ───────────────────────────────────
    # TODO: Create a FileSensor that:
    #   - watches CONFIG_FILE ("/tmp/forex/currencies.json")
    #   - uses mode="reschedule"  ← why is this important?
    #   - poke_interval=5, timeout=60
    check_config_file = FileSensor(
        task_id="check_config_file",
        # TODO: fill in the parameters
    )

    # ── Task 3: Fetch rates from the API ──────────────────────────────────────
    def fetch_forex_rates(**context):
        """
        Read the config file, call the API, push results to XCom.

        TODO:
        1. Open CONFIG_FILE and load the JSON (base currency + currency list)
        2. Create an HttpHook with http_conn_id="forex_api"
        3. Call hook.run(endpoint=...) with the API key in the path
        4. Check data["result"] == "success" — raise ValueError if not
        5. Filter conversion_rates to only the currencies in the config
        6. Push "rates" and "base_currency" to XCom via context["ti"].xcom_push
        7. Return selected_rates
        """
        # TODO: implement this function
        pass

    fetch_rates = PythonOperator(
        task_id="fetch_forex_rates",
        python_callable=fetch_forex_rates,
    )

    # ── Task 4: Write rates to CSV ────────────────────────────────────────────
    def save_rates_to_csv(**context):
        """
        Pull rates from XCom, write one row per currency to a CSV file.

        TODO:
        1. Pull "rates" and "base_currency" from XCom (task_ids="fetch_forex_rates")
        2. Build the CSV path: f"{DATA_DIR}/forex_rates_{context['ds_nodash']}.csv"
        3. Write rows: base_currency, target_currency, rate, fetched_at (= context["ts"])
        4. Push "csv_path" to XCom so downstream tasks know where the file is
        """
        # TODO: implement this function
        pass

    write_csv = PythonOperator(
        task_id="save_rates_to_csv",
        python_callable=save_rates_to_csv,
    )

    # ── Task 5: Create the PostgreSQL table ───────────────────────────────────
    # TODO: Create a PostgresOperator that runs CREATE TABLE IF NOT EXISTS.
    #   Columns: id (SERIAL PK), base_currency, target_currency,
    #            rate (NUMERIC), fetched_at (TIMESTAMP), execution_date (DATE).
    #   Also create an index on execution_date.
    create_forex_table = PostgresOperator(
        task_id="create_forex_table",
        postgres_conn_id="forex_postgres",
        sql="""
            -- TODO: write the CREATE TABLE IF NOT EXISTS statement here
        """,
    )

    # ── Task 6: Load CSV rows into PostgreSQL ─────────────────────────────────
    def load_rates_to_postgres(**context):
        """
        Pull csv_path from XCom, read the CSV, insert rows into forex_rates.

        TODO:
        1. Pull "csv_path" from XCom (task_ids="save_rates_to_csv")
        2. Raise FileNotFoundError if the file doesn't exist
        3. Use PostgresHook(postgres_conn_id="forex_postgres").get_conn() for the connection
        4. INSERT each row — use ON CONFLICT DO NOTHING for idempotency
        5. Commit, close cursor and connection
        6. Push "rows_inserted" to XCom
        """
        # TODO: implement this function
        pass

    insert_rates = PythonOperator(
        task_id="load_rates_to_postgres",
        python_callable=load_rates_to_postgres,
    )

    # ── Task 7: Log the email summary ─────────────────────────────────────────
    def send_summary_email(**context):
        """
        Pull rates and row count from XCom, compose and print the summary.

        TODO:
        1. Pull "rates" and "base_currency" from task "fetch_forex_rates"
        2. Pull "rows_inserted" from task "load_rates_to_postgres"
        3. Build a summary string listing each currency and its rate
        4. Print it — in production you'd call airflow.utils.email.send_email
        """
        # TODO: implement this function
        pass

    send_notification = PythonOperator(
        task_id="send_summary_email",
        python_callable=send_summary_email,
    )

    # ── Task 8: Clean up the temp CSV ─────────────────────────────────────────
    cleanup = BashOperator(
        task_id="cleanup_csv",
        bash_command="rm -f {{ ti.xcom_pull(task_ids='save_rates_to_csv', key='csv_path') }}",
        trigger_rule="all_done",    # TODO: why "all_done" instead of the default "all_success"?
    )

    # ── Task dependencies ──────────────────────────────────────────────────────
    # TODO: wire all 8 tasks together in the correct order.
    # Remember: check_api_availability AND check_config_file must BOTH complete
    # before fetch_rates can start.
    #
    # Sketch the graph first, then write the >> expressions.
