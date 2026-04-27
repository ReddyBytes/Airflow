# PostgresOperator — Theory

## Your Pipeline Meets the Database

Your pipeline extracts data from an API, transforms it in Python, and now needs to persist it somewhere. That somewhere is usually a database — and for most data teams, that database is PostgreSQL.

**PostgresOperator lets you run SQL directly from your DAG.** Create tables before loading data, insert records after transforming them, run stored procedures to aggregate results, or clean up stale data at the end.

Think of it like having a database administrator (DBA) on your pipeline team. You tell them what SQL to run and when. They connect to the database, execute the statement, and report back. You don't have to manage the connection yourself — Airflow handles that through its connection management system.

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Setting Up the Connection](#prerequisites-setting-up-the-postgres-connection) · [postgres_conn_id Parameter](#the-postgres_conn_id-parameter) · [sql Parameter](#the-sql-parameter)

**Should Learn** — important for real projects and interviews:
[Jinja Templating in SQL](#jinja-templating-in-sql) · [When to Use PostgresOperator](#when-to-use-postgresoperator) · [Full Working Code Example](#full-working-code-example)

**Good to Know** — useful in specific situations, not needed daily:
[autocommit](#autocommit) · [Safe Bind Variables](#using-parameters-for-safe-bind-variables)

**Reference** — skim once, look up when needed:
[Connection via Environment Variable](#step-3-or-add-the-connection-via-environment-variable)

---

## Prerequisites: Setting Up the Postgres Connection

Before you can use `PostgresOperator`, you need to tell Airflow how to reach your database. This is done through Airflow's **Connections** system.

### Step 1: Install the Postgres provider

```bash
pip install apache-airflow-providers-postgres
```

### Step 2: Add the connection in the Airflow UI

1. Go to **Admin → Connections** in the Airflow UI
2. Click the **+** button to add a new connection
3. Fill in:

| Field | Value |
|---|---|
| Connection Id | `my_postgres` (you reference this in your DAG) |
| Connection Type | `Postgres` |
| Host | `localhost` (or your DB host) |
| Schema | `mydb` (the database name) |
| Login | `myuser` |
| Password | `mypassword` |
| Port | `5432` |

4. Click **Save**

### Step 3: Or add the connection via environment variable

```bash
# Format: postgresql://user:password@host:port/dbname
export AIRFLOW_CONN_MY_POSTGRES="postgresql://myuser:mypassword@localhost:5432/mydb"
```

---

## The postgres_conn_id Parameter

This tells the operator which connection to use:

```python
from airflow.providers.postgres.operators.postgres import PostgresOperator

create_table = PostgresOperator(
    task_id="create_table",
    postgres_conn_id="my_postgres",  # Must match the Connection Id you set up
    sql="""
        CREATE TABLE IF NOT EXISTS daily_sales (
            id SERIAL PRIMARY KEY,
            sale_date DATE NOT NULL,
            amount DECIMAL(10, 2),
            region VARCHAR(50)
        );
    """,
)
```

---

## The sql Parameter

The `sql` parameter accepts:

**An inline SQL string:**
```python
sql="SELECT COUNT(*) FROM orders WHERE date = '{{ ds }}'"
```

**A multi-statement string:**
```python
sql="""
    BEGIN;
    UPDATE orders SET processed = TRUE WHERE date = '{{ ds }}';
    INSERT INTO audit_log (event, occurred_at) VALUES ('orders_processed', NOW());
    COMMIT;
"""
```

**A path to a SQL file** (relative to the DAGs folder):
```python
sql="sql/create_tables.sql"
```

**A list of SQL statements:**
```python
sql=[
    "DELETE FROM staging WHERE date < '{{ ds }}'",
    "INSERT INTO staging SELECT * FROM raw WHERE date = '{{ ds }}'",
    "ANALYZE staging",
]
```

---

## Jinja Templating in SQL

Like all Airflow operators, PostgresOperator supports Jinja templating in the `sql` parameter:

```python
PostgresOperator(
    task_id="load_daily_data",
    postgres_conn_id="my_postgres",
    sql="""
        INSERT INTO daily_metrics (date, total_orders, total_revenue)
        SELECT
            '{{ ds }}'::DATE,
            COUNT(*),
            SUM(amount)
        FROM raw_orders
        WHERE order_date = '{{ ds }}';
    """,
)
```

`{{ ds }}` is replaced with the execution date (`YYYY-MM-DD`) at runtime.

---

## Using parameters for Safe Bind Variables

For dynamic values that come from Python (not Jinja templates), use `parameters` to avoid SQL injection:

```python
PostgresOperator(
    task_id="insert_record",
    postgres_conn_id="my_postgres",
    sql="INSERT INTO logs (message, level) VALUES (%s, %s)",
    parameters=("Pipeline started", "INFO"),
)
```

Note: `parameters` uses `%s` placeholders (psycopg2 style), not `{{ }}`.

---

## autocommit

By default, `PostgresOperator` wraps statements in a transaction. You can disable this for DDL statements (like `CREATE TABLE`) that cannot run inside a transaction in some Postgres configurations:

```python
PostgresOperator(
    task_id="create_index",
    postgres_conn_id="my_postgres",
    sql="CREATE INDEX CONCURRENTLY idx_orders_date ON orders(date);",
    autocommit=True,  # CREATE INDEX CONCURRENTLY can't run in a transaction
)
```

---

## Full Working Code Example

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.python import PythonOperator

with DAG(
    dag_id="postgres_operator_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
) as dag:

    # Step 1: Ensure the target table exists
    create_table = PostgresOperator(
        task_id="create_staging_table",
        postgres_conn_id="my_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS staging_orders (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) UNIQUE,
                customer_id INT,
                amount DECIMAL(10, 2),
                order_date DATE,
                loaded_at TIMESTAMP DEFAULT NOW()
            );
        """,
    )

    # Step 2: Clear today's data (idempotent load)
    clear_today = PostgresOperator(
        task_id="clear_todays_staging",
        postgres_conn_id="my_postgres",
        sql="DELETE FROM staging_orders WHERE order_date = '{{ ds }}';",
    )

    # Step 3: Load data (in a real DAG, you'd use a transfer operator or XCom)
    load_data = PostgresOperator(
        task_id="load_orders",
        postgres_conn_id="my_postgres",
        sql="""
            INSERT INTO staging_orders (order_id, customer_id, amount, order_date)
            SELECT order_id, customer_id, amount, order_date
            FROM raw_orders
            WHERE order_date = '{{ ds }}'
              AND is_valid = TRUE;
        """,
    )

    # Step 4: Validate the load
    validate_load = PostgresOperator(
        task_id="validate_load",
        postgres_conn_id="my_postgres",
        sql="""
            DO $$
            DECLARE
                row_count INT;
            BEGIN
                SELECT COUNT(*) INTO row_count
                FROM staging_orders
                WHERE order_date = '{{ ds }}';

                IF row_count = 0 THEN
                    RAISE EXCEPTION 'No rows loaded for date {{ ds }}';
                ELSE
                    RAISE NOTICE 'Validation passed: % rows for {{ ds }}', row_count;
                END IF;
            END $$;
        """,
    )

    create_table >> clear_today >> load_data >> validate_load
```

---

## When to Use PostgresOperator

**Good for:**
- Running DDL (CREATE TABLE, ALTER TABLE, CREATE INDEX)
- Running DML (INSERT, UPDATE, DELETE, MERGE)
- Calling stored procedures
- Running validation queries
- Any SQL that lives in a `.sql` file

**Not ideal for:**
- Returning large result sets to the DAG (use `PostgresHook` instead)
- Dynamic SQL that requires complex Python logic (use `PythonOperator` with `PostgresHook`)
- Cross-database operations

---

## Navigation

**Prev:** [PythonOperator Theory](../02_PythonOperator/Theory.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [S3Operator Theory](../04_S3Operator/Theory.md)
