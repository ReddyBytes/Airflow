# Data Quality Pipeline — Step by Step

You are a senior data engineer. After a null `customer_id` sneaked past your ETL
last month and corrupted the weekly revenue report, your team has decided: **no data
enters the warehouse without validation**. This pipeline implements that policy.

---

## What You Will Build

```
extract_from_postgres
        ↓
validate_with_great_expectations
        ↓
   [branch]
    /      \
load_to_    send_
warehouse   alert
```

Tasks:
1. **Extract** — query Postgres staging table into a Pandas DataFrame
2. **Validate** — run Great Expectations checks
3. **Branch** — route on pass/fail
4. **Load** — insert clean rows into the warehouse (on pass)
5. **Alert** — send a Slack/email notification (on fail)

---

## Prerequisites

```bash
pip install apache-airflow[postgres] \
            great-expectations \
            apache-airflow-providers-great-expectations \
            apache-airflow-providers-postgres
```

Airflow connections needed:
- `postgres_staging` — Postgres staging DB
- `postgres_warehouse` — Postgres warehouse DB

---

## Step 1 — Create Staging and Warehouse Tables

```sql
-- Run on your Postgres instance

-- Staging (raw ingest)
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id    TEXT PRIMARY KEY,
    customer_id TEXT,
    amount      NUMERIC(12,2),
    currency    VARCHAR(3),
    status      TEXT,
    order_date  DATE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Warehouse (clean, validated)
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE TABLE IF NOT EXISTS warehouse.orders (
    order_id     TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    currency     VARCHAR(3),
    status       TEXT,
    order_date   DATE,
    loaded_at    TIMESTAMPTZ DEFAULT NOW()
);
```

Insert some test data with intentional quality issues:
```sql
INSERT INTO staging.orders VALUES
  ('ORD-001', 'CUST-A', 100.00, 'USD', 'shipped', '2024-01-15', NOW()),
  ('ORD-002', NULL,      50.00, 'USD', 'pending', '2024-01-15', NOW()),   -- null customer_id
  ('ORD-003', 'CUST-C', -5.00, 'USD', 'shipped', '2024-01-15', NOW()),   -- negative amount
  ('ORD-004', 'CUST-D', 200.00,'USD', 'shipped', '2024-01-15', NOW());
```

---

## Step 2 — Create the Great Expectations Suite

```python
# scripts/create_orders_suite.py  (run once)
import great_expectations as gx

context = gx.get_context(context_root_dir="/opt/airflow/great_expectations")

suite = context.add_or_update_expectation_suite("orders_quality_suite")

validator = context.get_validator(
    batch_request={
        "datasource_name": "postgres_staging",
        "data_connector_name": "default_inferred",
        "data_asset_name": "staging.orders",
    },
    expectation_suite_name="orders_quality_suite",
)

validator.expect_table_row_count_to_be_between(min_value=1)
validator.expect_column_values_to_not_be_null("order_id")
validator.expect_column_values_to_not_be_null("customer_id")
validator.expect_column_values_to_be_unique("order_id")
validator.expect_column_values_to_be_between("amount", min_value=0.01)
validator.expect_column_values_to_be_in_set(
    "currency", ["USD", "EUR", "GBP", "JPY", "CAD"]
)
validator.expect_column_values_to_be_in_set(
    "status", ["pending", "shipped", "delivered", "cancelled", "refunded"]
)

validator.save_expectation_suite(discard_failed_expectations=False)
print("Suite saved to great_expectations/expectations/orders_quality_suite.json")
```

Run it:
```bash
cd /opt/airflow && python scripts/create_orders_suite.py
```

---

## Step 3 — Configure the GX Checkpoint

Create `/opt/airflow/great_expectations/checkpoints/orders_checkpoint.yml`:

```yaml
name: orders_checkpoint
config_version: 1
class_name: Checkpoint
run_name_template: "%Y%m%d-%H%M%S-orders"
expectation_suite_name: orders_quality_suite

batch_request:
  datasource_name: postgres_staging
  data_connector_name: default_inferred
  data_asset_name: staging.orders

action_list:
  - name: store_validation_result
    action:
      class_name: StoreValidationResultAction
  - name: update_data_docs
    action:
      class_name: UpdateDataDocsAction
```

---

## Step 4 — Write the DAG

Create `/opt/airflow/dags/data_quality_pipeline.py`:

```python
from datetime import datetime, timedelta
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.email import EmailOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator


def extract_to_staging(**context):
    """Verify staging data exists for today's date."""
    hook = PostgresHook(postgres_conn_id="postgres_staging")
    count = hook.get_first(
        "SELECT COUNT(*) FROM staging.orders WHERE order_date = %s",
        parameters=[context["ds"]],
    )[0]
    print(f"Found {count} rows in staging for {context['ds']}")
    if count == 0:
        raise ValueError(f"No staging data for {context['ds']}")
    context["ti"].xcom_push(key="staging_row_count", value=count)


def branch_on_validation(**context):
    result = context["ti"].xcom_pull(task_ids="validate_data")
    if result and result.get("success"):
        return "load_to_warehouse"
    return "send_failure_alert"


def load_clean_rows(**context):
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")
    rows_loaded = hook.run("""
        INSERT INTO warehouse.orders
            (order_id, customer_id, amount, currency, status, order_date)
        SELECT order_id, customer_id, amount, currency, status, order_date
        FROM staging.orders
        WHERE order_date = %(ds)s
          AND customer_id IS NOT NULL
          AND amount >= 0
        ON CONFLICT (order_id) DO UPDATE
            SET amount     = EXCLUDED.amount,
                status     = EXCLUDED.status,
                loaded_at  = NOW()
    """, parameters={"ds": context["ds"]})
    print(f"Load complete for {context['ds']}")


with DAG(
    dag_id="data_quality_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["intermediate", "data-quality"],
) as dag:

    check_staging = PythonOperator(
        task_id="check_staging",
        python_callable=extract_to_staging,
    )

    validate = GreatExpectationsOperator(
        task_id="validate_data",
        checkpoint_name="orders_checkpoint",
        data_context_root_dir="/opt/airflow/great_expectations",
        fail_task_on_validation_failure=False,
        return_json_dict=True,
    )

    branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=branch_on_validation,
    )

    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_clean_rows,
    )

    alert = EmailOperator(
        task_id="send_failure_alert",
        to="data-team@company.com",
        subject="Data Quality FAILED — {{ ds }}",
        html_content="<p>Validation failed for {{ ds }}. Check GX Data Docs.</p>",
    )

    check_staging >> validate >> branch >> [load, alert]
```

---

## Step 5 — Trigger and Observe

```bash
airflow dags trigger data_quality_pipeline --exec-date 2024-01-15
```

With the test data inserted in Step 1 (2 bad rows out of 4), the GX suite will
fail because `expect_column_values_to_not_be_null("customer_id")` catches the
null and `expect_column_values_to_be_between("amount", min_value=0.01)` catches
the negative amount.

Expected flow: `check_staging → validate_data → branch_on_quality → send_failure_alert`

Now fix the data and re-trigger:
```sql
DELETE FROM staging.orders WHERE order_id IN ('ORD-002', 'ORD-003');
```

Re-trigger → `check_staging → validate_data → branch_on_quality → load_to_warehouse`

---

## Step 6 — Verify the Warehouse

```sql
SELECT * FROM warehouse.orders ORDER BY order_id;
-- Should see ORD-001 and ORD-004 only
```

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Full Code** | [Code_Example.md](./Code_Example.md) |
| **Parent: Intermediate Projects** | [02_Intermediate_Projects](../Readme.md) |
| **Previous: File Processing** | [02_Simple_File_Processing](../../01_Beginner_Projects/02_Simple_File_Processing/Project_Guide.md) |
| **Next: Multi-Source ETL** | [04_Multi_Source_ETL](../04_Multi_Source_ETL/Project_Guide.md) |
