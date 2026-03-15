# PostgresOperator — Cheatsheet

Quick reference for running SQL against PostgreSQL from an Airflow DAG. Parameters, patterns, and the key decisions you need to make every time you use this operator.

---

## What It Does in One Sentence

Executes SQL statements against a PostgreSQL database using a stored Airflow connection — no boilerplate connection code required.

---

## Provider Package

```bash
pip install apache-airflow-providers-postgres
```

Not part of Airflow core. Must be installed separately.

---

## Import

```python
from airflow.providers.postgres.operators.postgres import PostgresOperator
```

---

## Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `postgres_conn_id` | `str` | `'postgres_default'` | Airflow connection ID pointing to your PostgreSQL instance |
| `sql` | `str \| list` | **required** | SQL string, list of SQL strings, or path to a `.sql` file |
| `parameters` | `tuple \| dict` | `None` | Bind variables for `%s` placeholders — prevents SQL injection |
| `autocommit` | `bool` | `False` | `True` = each statement commits immediately; required for `CREATE INDEX CONCURRENTLY` etc. |
| `database` | `str` | `None` | Override the database in the connection |

---

## Template Fields (Jinja-aware)

`sql`, `parameters` — support `{{ ds }}`, `{{ run_id }}`, `{{ var.value.x }}`, etc.

---

## Code Patterns

### Single SQL Statement

```python
PostgresOperator(
    task_id="create_table",
    postgres_conn_id="my_postgres",
    sql="""
        CREATE TABLE IF NOT EXISTS daily_orders (
            id SERIAL PRIMARY KEY,
            order_date DATE,
            total DECIMAL(12, 2)
        );
    """,
)
```

---

### Jinja-Templated SQL

```python
PostgresOperator(
    task_id="load_daily",
    postgres_conn_id="my_postgres",
    sql="""
        INSERT INTO daily_orders (order_date, total)
        SELECT '{{ ds }}'::DATE, SUM(amount)
        FROM raw_orders
        WHERE order_date = '{{ ds }}';
    """,
)
```

---

### Multiple Statements (List)

```python
PostgresOperator(
    task_id="idempotent_load",
    postgres_conn_id="my_postgres",
    sql=[
        "DELETE FROM staging WHERE run_date = '{{ ds }}'",
        "INSERT INTO staging SELECT * FROM raw WHERE date = '{{ ds }}'",
        "UPDATE staging SET processed = TRUE WHERE run_date = '{{ ds }}'",
    ],
)
```

---

### Using a `.sql` File

```python
PostgresOperator(
    task_id="run_from_file",
    postgres_conn_id="my_postgres",
    sql="sql/setup_tables.sql",    # relative to dags/ folder; supports Jinja
)
```

---

### Bind Variables (Safe Parameterization)

```python
PostgresOperator(
    task_id="insert_event",
    postgres_conn_id="my_postgres",
    sql="INSERT INTO events (event_name, occurred_at) VALUES (%s, %s)",
    parameters=("dag_started", "{{ ts }}"),    # %s style, NOT {{ }}
)
```

---

### DDL That Requires autocommit

```python
PostgresOperator(
    task_id="concurrent_index",
    postgres_conn_id="my_postgres",
    sql="CREATE INDEX CONCURRENTLY idx_orders_date ON orders(order_date);",
    autocommit=True,    # required — cannot run inside a transaction
)
```

---

## Idempotent Load Pattern

```python
# Safe to re-run: delete first, then reload
load = PostgresOperator(
    task_id="reload_partition",
    postgres_conn_id="my_postgres",
    sql=[
        "DELETE FROM fact_sales WHERE sale_date = '{{ ds }}'",
        "INSERT INTO fact_sales SELECT * FROM stg_sales WHERE date = '{{ ds }}'",
    ],
)
```

---

## When to Use PostgresOperator

| Use it when... | Avoid it when... |
|---|---|
| Running DDL (CREATE, ALTER, DROP) | You need query results back in Python |
| Running DML (INSERT, UPDATE, DELETE) | Complex conditional SQL logic based on Python vars |
| Calling stored procedures | Need to page through large result sets |
| Loading from a `.sql` file | Cross-database or dynamic schema operations |
| Any "fire and forget" SQL task | You need UPSERT logic driven by Python |

For query results, use **PythonOperator + PostgresHook** instead:
```python
from airflow.providers.postgres.hooks.postgres import PostgresHook
hook = PostgresHook(postgres_conn_id="my_postgres")
rows = hook.get_records("SELECT * FROM orders WHERE date = %s", ("2024-01-15",))
```

---

## Common Pitfalls

1. **Mixing `%s` and `{{ }}` syntax** — `parameters` uses `%s` (psycopg2); Jinja uses `{{ }}`; they are separate rendering systems
2. **Forgetting `autocommit=True` for DDL** — `CREATE INDEX CONCURRENTLY`, `CREATE DATABASE`, `VACUUM` fail inside a transaction
3. **Non-idempotent SQL** — always design tasks to be safely re-runnable; use `IF NOT EXISTS`, `DELETE + INSERT`, or `UPSERT`
4. **Large result sets** — PostgresOperator does not return data to Python; use PostgresHook or `COPY TO` for exports
5. **Wrong import path** — use `airflow.providers.postgres...`, not the old `airflow.operators.postgres_operator` (removed in Airflow 2+)

---

## Golden Rules

- Always use `%s` bind variables for dynamic values, never string formatting — prevents SQL injection
- Design every task to be idempotent — `DELETE WHERE date = X` before `INSERT WHERE date = X`
- Use `autocommit=True` for any PostgreSQL DDL that cannot run inside a transaction
- Keep complex SQL in `.sql` files, not inline Python strings — easier to test and version control
- For anything that reads data back into Python, reach for PostgresHook instead of this operator

---

## Connection Setup Quick Reference

```bash
# Via environment variable
export AIRFLOW_CONN_MY_POSTGRES="postgresql://user:pass@host:5432/dbname"

# Via Airflow UI: Admin > Connections > +
# Connection Type: Postgres
# Connection Id: my_postgres
# Host: your-db-host
# Schema: your_database_name
# Login: your_user
# Password: your_password
# Port: 5432
```

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview prep |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [02_PythonOperator](../02_PythonOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [04_S3Operator](../04_S3Operator/Theory.md)
