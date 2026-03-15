# PostgresOperator — Code Examples

## Example 1: CREATE TABLE

Set up your database schema before loading data. Use `IF NOT EXISTS` to make your DAG idempotent (safe to re-run).

```python
from datetime import datetime
from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator

with DAG(
    dag_id="postgres_create_tables",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@once",   # Run once to set up schema
    catchup=False,
    tags=["postgres", "ddl", "example"],
) as dag:

    # Create a simple orders table
    create_orders_table = PostgresOperator(
        task_id="create_orders_table",
        postgres_conn_id="my_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS orders (
                order_id     VARCHAR(50)    PRIMARY KEY,
                customer_id  INT            NOT NULL,
                product_sku  VARCHAR(20)    NOT NULL,
                quantity     INT            NOT NULL DEFAULT 1,
                unit_price   DECIMAL(10, 2) NOT NULL,
                total_amount DECIMAL(10, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
                order_date   DATE           NOT NULL,
                status       VARCHAR(20)    NOT NULL DEFAULT 'pending',
                created_at   TIMESTAMP      NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMP      NOT NULL DEFAULT NOW()
            );
        """,
    )

    # Create a summary/aggregation table
    create_daily_summary_table = PostgresOperator(
        task_id="create_daily_summary_table",
        postgres_conn_id="my_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS daily_order_summary (
                summary_date    DATE           PRIMARY KEY,
                total_orders    INT            NOT NULL DEFAULT 0,
                total_revenue   DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
                avg_order_value DECIMAL(10, 2),
                unique_customers INT,
                last_updated    TIMESTAMP      NOT NULL DEFAULT NOW()
            );
        """,
    )

    # Create an audit log table
    create_audit_table = PostgresOperator(
        task_id="create_audit_table",
        postgres_conn_id="my_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS pipeline_audit (
                id           SERIAL         PRIMARY KEY,
                pipeline_name VARCHAR(100)   NOT NULL,
                run_date     DATE           NOT NULL,
                rows_inserted INT           DEFAULT 0,
                rows_updated  INT           DEFAULT 0,
                status       VARCHAR(20)    NOT NULL,
                message      TEXT,
                executed_at  TIMESTAMP      NOT NULL DEFAULT NOW()
            );

            -- Index for common query pattern
            CREATE INDEX IF NOT EXISTS idx_audit_run_date
                ON pipeline_audit(run_date, pipeline_name);
        """,
    )

    # Run table creation in sequence
    create_orders_table >> create_daily_summary_table >> create_audit_table
```

---

## Example 2: INSERT Data from Previous Task via XCom

Combine `PythonOperator` and `PostgresOperator` in a real ETL pattern. The Python task fetches and transforms data; the SQL task loads it.

```python
from datetime import datetime, timedelta
import json
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook


def fetch_and_transform_orders(**context):
    """
    Simulates fetching data from an API and transforming it.
    Returns a list of tuples ready for DB insertion.
    """
    execution_date = context["ds"]
    print(f"Fetching orders for {execution_date}")

    # Simulate API response
    raw_orders = [
        {"id": "ORD-001", "customer": 101, "sku": "PROD-A", "qty": 2, "price": 49.99},
        {"id": "ORD-002", "customer": 102, "sku": "PROD-B", "qty": 1, "price": 99.99},
        {"id": "ORD-003", "customer": 101, "sku": "PROD-C", "qty": 3, "price": 29.99},
    ]

    # Transform: convert to list of dicts with all required fields
    transformed = []
    for order in raw_orders:
        transformed.append({
            "order_id": order["id"],
            "customer_id": order["customer"],
            "product_sku": order["sku"],
            "quantity": order["qty"],
            "unit_price": order["price"],
            "order_date": execution_date,
            "status": "pending",
        })

    print(f"Transformed {len(transformed)} records")
    return transformed  # Pushed to XCom as 'return_value'


def insert_orders_via_hook(**context):
    """
    Uses PostgresHook directly to insert the records from XCom.
    This approach is better when you need to insert many rows efficiently.
    """
    ti = context["ti"]
    records = ti.xcom_pull(task_ids="fetch_and_transform_orders")

    if not records:
        print("No records to insert")
        return 0

    hook = PostgresHook(postgres_conn_id="my_postgres")

    insert_sql = """
        INSERT INTO orders (order_id, customer_id, product_sku, quantity, unit_price, order_date, status)
        VALUES (%(order_id)s, %(customer_id)s, %(product_sku)s, %(quantity)s, %(unit_price)s, %(order_date)s, %(status)s)
        ON CONFLICT (order_id) DO UPDATE SET
            status = EXCLUDED.status,
            updated_at = NOW()
    """

    # Insert all records in one transaction
    conn = hook.get_conn()
    cursor = conn.cursor()
    try:
        cursor.executemany(insert_sql, records)
        conn.commit()
        print(f"Successfully inserted/updated {cursor.rowcount} records")
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


with DAG(
    dag_id="postgres_insert_from_xcom",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["postgres", "xcom", "etl", "example"],
) as dag:

    # Step 1: Create table (idempotent)
    create_table = PostgresOperator(
        task_id="ensure_table_exists",
        postgres_conn_id="my_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS orders (
                order_id    VARCHAR(50)    PRIMARY KEY,
                customer_id INT            NOT NULL,
                product_sku VARCHAR(20)    NOT NULL,
                quantity    INT            NOT NULL,
                unit_price  DECIMAL(10,2)  NOT NULL,
                order_date  DATE           NOT NULL,
                status      VARCHAR(20)    NOT NULL,
                updated_at  TIMESTAMP      NOT NULL DEFAULT NOW()
            );
        """,
    )

    # Step 2: Fetch and transform data in Python
    fetch_transform = PythonOperator(
        task_id="fetch_and_transform_orders",
        python_callable=fetch_and_transform_orders,
    )

    # Step 3: Insert using PostgresHook in Python (more control for bulk insert)
    insert = PythonOperator(
        task_id="insert_orders",
        python_callable=insert_orders_via_hook,
    )

    # Step 4: Update summary table using SQL after load
    update_summary = PostgresOperator(
        task_id="update_daily_summary",
        postgres_conn_id="my_postgres",
        sql="""
            INSERT INTO daily_order_summary (summary_date, total_orders, total_revenue, avg_order_value, unique_customers)
            SELECT
                order_date,
                COUNT(*),
                SUM(quantity * unit_price),
                AVG(quantity * unit_price),
                COUNT(DISTINCT customer_id)
            FROM orders
            WHERE order_date = '{{ ds }}'
            ON CONFLICT (summary_date) DO UPDATE SET
                total_orders    = EXCLUDED.total_orders,
                total_revenue   = EXCLUDED.total_revenue,
                avg_order_value = EXCLUDED.avg_order_value,
                unique_customers = EXCLUDED.unique_customers,
                last_updated    = NOW();
        """,
    )

    create_table >> fetch_transform >> insert >> update_summary
```

---

## Example 3: Multiple SQL Statements

Run several SQL statements in one task using a list or a multi-statement string.

```python
from datetime import datetime
from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator

with DAG(
    dag_id="postgres_multi_sql",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["postgres", "multi-sql", "example"],
) as dag:

    # Option A: List of SQL statements (each runs separately)
    cleanup_and_stage = PostgresOperator(
        task_id="cleanup_and_stage",
        postgres_conn_id="my_postgres",
        sql=[
            # Statement 1: Remove today's data (make it safe to re-run)
            "DELETE FROM staging_orders WHERE order_date = '{{ ds }}';",

            # Statement 2: Copy from raw into staging
            """
            INSERT INTO staging_orders (order_id, customer_id, amount, order_date)
            SELECT order_id, customer_id, amount, date
            FROM raw_orders
            WHERE date = '{{ ds }}'
              AND status != 'cancelled';
            """,

            # Statement 3: Log the action
            """
            INSERT INTO pipeline_audit (pipeline_name, run_date, status, message)
            VALUES ('daily_orders', '{{ ds }}', 'staged', 'Staging load complete');
            """,
        ],
    )

    # Option B: Multi-statement string with a PL/pgSQL block for complex logic
    validate_and_promote = PostgresOperator(
        task_id="validate_and_promote_to_production",
        postgres_conn_id="my_postgres",
        sql="""
            DO $$
            DECLARE
                staged_count INT;
                prod_count INT;
            BEGIN
                -- Count staged records
                SELECT COUNT(*) INTO staged_count
                FROM staging_orders
                WHERE order_date = '{{ ds }}';

                -- Ensure we have data
                IF staged_count = 0 THEN
                    RAISE EXCEPTION 'No staged data for {{ ds }} — aborting promotion';
                END IF;

                RAISE NOTICE 'Promoting % records to production...', staged_count;

                -- Delete any existing production records for this date (idempotent)
                DELETE FROM production_orders WHERE order_date = '{{ ds }}';

                -- Promote staging to production
                INSERT INTO production_orders
                SELECT * FROM staging_orders WHERE order_date = '{{ ds }}';

                GET DIAGNOSTICS prod_count = ROW_COUNT;

                -- Verify row counts match
                IF prod_count != staged_count THEN
                    RAISE EXCEPTION 'Row count mismatch: staged=%, promoted=%',
                        staged_count, prod_count;
                END IF;

                -- Update audit log
                UPDATE pipeline_audit
                SET status = 'promoted', rows_inserted = prod_count,
                    message = format('Promoted %s records', prod_count)
                WHERE pipeline_name = 'daily_orders' AND run_date = '{{ ds }}';

                RAISE NOTICE 'Promotion complete: % records', prod_count;
            END $$;
        """,
        autocommit=False,  # Run the whole block in a transaction
    )

    # Option C: Reference an external SQL file
    # (file lives at dags/sql/generate_weekly_report.sql)
    weekly_aggregation = PostgresOperator(
        task_id="generate_weekly_aggregation",
        postgres_conn_id="my_postgres",
        sql="sql/weekly_aggregation.sql",  # Relative to AIRFLOW_HOME/dags/
    )

    cleanup_and_stage >> validate_and_promote >> weekly_aggregation
```

**What to notice:**
- Pass a **list** of strings to `sql` to run multiple independent statements
- Use a **single string** with multiple statements (separated by `;`) for a block
- Use `DO $$ ... $$` for PL/pgSQL procedural logic with variables and error handling
- Use `{{ ds }}` for Jinja date templating in SQL
- Store complex SQL in `.sql` files and reference them by path for cleaner DAGs
- `ON CONFLICT ... DO UPDATE` makes inserts idempotent (safe to re-run)
