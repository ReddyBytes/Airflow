# 03 — Step-by-Step Guide: Data Quality Gate Pipeline

Build the pipeline in 6 steps. This guide shows you the setup in detail
(GX configuration is non-obvious the first time) and then leaves the
Airflow DAG wiring for you to work out with hints.

---

## Step 1 — Create the Staging and Warehouse Tables

Run this on your PostgreSQL instance:

```sql
-- Staging (raw ingest — may contain quality issues)
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

-- Warehouse (clean, validated data only)
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

Insert test data with intentional quality issues:
```sql
INSERT INTO staging.orders VALUES
  ('ORD-001', 'CUST-A', 100.00, 'USD', 'shipped',   '2024-01-15', NOW()),
  ('ORD-002', NULL,      50.00, 'USD', 'pending',   '2024-01-15', NOW()),  -- null customer_id
  ('ORD-003', 'CUST-C', -5.00, 'USD', 'shipped',   '2024-01-15', NOW()),  -- negative amount
  ('ORD-004', 'CUST-D', 200.00,'USD', 'shipped',   '2024-01-15', NOW());
```

---

## Step 2 — Create the Great Expectations Suite

Run this once as a setup script (not inside the DAG):

```python
# scripts/create_orders_suite.py
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
    "status", ["pending", "shipped", "delivered", "cancelled", "refunded"]
)

validator.save_expectation_suite(discard_failed_expectations=False)
print("Suite created: great_expectations/expectations/orders_quality_suite.json")
```

```bash
cd /opt/airflow && python scripts/create_orders_suite.py
```

---

## Step 3 — Create the GX Checkpoint

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

## Step 4 — Build the check_staging Task

Write a `check_staging_data` callable that confirms staging rows exist for
the logical date. This is a fail-fast guard — if there's no data, there's
nothing to validate and it's better to fail immediately with a clear error
than to have GX run on an empty dataset.

<details>
<summary>💡 Hint — PostgresHook.get_first</summary>

```python
hook = PostgresHook(postgres_conn_id="postgres_staging")
count = hook.get_first(
    "SELECT COUNT(*) FROM staging.orders WHERE order_date = %s",
    parameters=[context["ds"]],
)[0]

if count == 0:
    raise ValueError(f"No staging data for {context['ds']}")
```

`get_first` returns a tuple — `[0]` extracts the count integer.

</details>

---

## Step 5 — Build the GreatExpectationsOperator

This is the core task. It runs the checkpoint you created in Step 3.

The two key parameters are:
- `fail_task_on_validation_failure=False` — the task succeeds even if GX finds
  failures, so downstream tasks (including the alert) still run
- `return_json_dict=True` — the result dict is pushed to XCom as the task's
  return value

<details>
<summary>✅ Answer — GreatExpectationsOperator</summary>

```python
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

validate = GreatExpectationsOperator(
    task_id="validate_data",
    checkpoint_name="orders_checkpoint",
    data_context_root_dir="/opt/airflow/great_expectations",
    checkpoint_kwargs={
        "batch_request": {
            "datasource_name": "postgres_staging",
            "data_connector_name": "default_inferred",
            "data_asset_name": "staging.orders",
        }
    },
    fail_task_on_validation_failure=False,  # ← let us route manually
    return_json_dict=True,                  # ← push result to XCom
)
```

</details>

---

## Step 6 — Build the Branch and Both Paths

**Branch task:** pull the GX result from XCom and route based on `result["success"]`.

<details>
<summary>💡 Hint — pulling GX result from XCom</summary>

`GreatExpectationsOperator` with `return_json_dict=True` stores its result as
the task's return value, which Airflow stores in XCom under key `"return_value"`.
Pull it with:

```python
result = context["ti"].xcom_pull(task_ids="validate_data")
# or explicitly:
result = context["ti"].xcom_pull(task_ids="validate_data", key="return_value")
```

Then read `result.get("success", False)` to know if all expectations passed.

</details>

**Load task:** insert from staging to warehouse using `PostgresHook`. Use
`ON CONFLICT (order_id) DO UPDATE` for idempotency.

<details>
<summary>💡 Hint — idempotent INSERT pattern</summary>

```python
hook = PostgresHook(postgres_conn_id="postgres_warehouse")
hook.run("""
    INSERT INTO warehouse.orders
        (order_id, customer_id, amount, currency, status, order_date)
    SELECT order_id, customer_id, amount, currency, status, order_date
    FROM staging.orders
    WHERE order_date    = %(ds)s
      AND customer_id   IS NOT NULL
      AND amount        >= 0.01
    ON CONFLICT (order_id) DO UPDATE
        SET amount    = EXCLUDED.amount,
            status    = EXCLUDED.status,
            loaded_at = NOW()
""", parameters={"ds": context["ds"]})
```

</details>

**Failure report task:** pull the GX result, extract `result["results"]` where
each item has `"success": False`, and build a plain-text summary.

**Email task:** use `EmailOperator`. The `html_content` can use a Jinja template
to pull the report from XCom.

<details>
<summary>💡 Hint — EmailOperator with XCom in html_content</summary>

```python
alert = EmailOperator(
    task_id="send_failure_alert",
    to="data-team@company.com",
    subject="[AIRFLOW] Data Quality FAILED — {{ ds }}",
    html_content="""
    <h2>Data Quality Validation Failed</h2>
    <p><strong>Date:</strong> {{ ds }}</p>
    <p>{{ task_instance.xcom_pull(task_ids='build_failure_report',
                                   key='failure_report') | replace('\\n', '<br>') }}</p>
    """,
)
```

</details>

**Convergence:** add an `EmptyOperator` with
`trigger_rule="none_failed_min_one_success"` as the final `pipeline_complete` task.

---

## Test Commands

```bash
# Trigger the DAG — with the test data (2 bad rows), GX should fail
airflow dags trigger data_quality_pipeline --exec-date 2024-01-15

# Fix the data and re-trigger → should load to warehouse
psql -U airflow -c "DELETE FROM staging.orders WHERE order_id IN ('ORD-002', 'ORD-003');"
airflow dags trigger data_quality_pipeline --exec-date 2024-01-15

# Verify warehouse loaded
psql -U airflow -c "SELECT * FROM warehouse.orders ORDER BY order_id;"
```

---

⬅️ **Prev:** [02 — Architecture](./02_ARCHITECTURE.md) &nbsp;&nbsp; ➡️ **Next:** [04 — Recap](./04_RECAP.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
