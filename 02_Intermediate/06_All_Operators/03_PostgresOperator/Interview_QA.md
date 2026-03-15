# PostgresOperator — Interview Q&A

Your pipeline writes results to PostgreSQL. Can you explain how Airflow manages that connection? How do you make the SQL dynamic? What happens in a transaction? These questions come up often.

---

## Beginner Questions

**Q1. What is PostgresOperator and what problem does it solve?**

PostgresOperator lets you run SQL statements against a PostgreSQL database directly from a DAG task. It solves the problem of managing database connections, credentials, and statement execution in your pipeline without writing boilerplate Python connection code.

Use it to create tables before loading data, insert or update records, run cleanup queries, or call stored procedures — all as first-class tasks with retry logic, logging, and dependency management built in.

```python
from airflow.providers.postgres.operators.postgres import PostgresOperator

create_table = PostgresOperator(
    task_id="create_staging_table",
    postgres_conn_id="my_postgres",
    sql="CREATE TABLE IF NOT EXISTS staging (id SERIAL, value TEXT);",
)
```

---

**Q2. What Airflow connection does PostgresOperator need? How do you set it up?**

It needs an Airflow **Postgres connection**, which stores the host, port, database name, username, and password securely in the Airflow metadata database.

Setting it up:
1. Install the provider: `pip install apache-airflow-providers-postgres`
2. Go to **Admin → Connections** in the Airflow UI
3. Add a new connection with type `Postgres`, fill in host, schema (database name), login, password, port

Or via environment variable:
```bash
export AIRFLOW_CONN_MY_POSTGRES="postgresql://user:pass@host:5432/dbname"
```

---

**Q3. What is `postgres_conn_id`?**

`postgres_conn_id` tells the operator which connection to look up in Airflow's connection store. It must match the **Connection Id** you created in the UI or the env var suffix:

```python
PostgresOperator(
    task_id="run_query",
    postgres_conn_id="my_postgres",   # must match your connection name
    sql="SELECT 1;",
)
```

The default value is `"postgres_default"` — if you name your connection that, you can omit the parameter.

---

**Q4. What is the `sql` parameter? What formats does it accept?**

`sql` is the SQL to execute. It accepts several formats:

- **Inline string**: `sql="SELECT COUNT(*) FROM orders"`
- **Multi-line string**: triple-quoted `"""..."""`
- **Path to a `.sql` file** relative to the DAGs folder: `sql="sql/create_tables.sql"`
- **List of statements**: `sql=["DELETE FROM staging", "INSERT INTO staging SELECT ..."]`

---

**Q5. What Python package do I need to install to use PostgresOperator?**

```bash
pip install apache-airflow-providers-postgres
```

This is a separate provider package — not included in Airflow core.

---

## Intermediate Questions

**Q6. How do you run parameterized SQL safely in PostgresOperator?**

Use the `parameters` parameter with `%s` placeholders — this uses psycopg2's bind variables under the hood and prevents SQL injection:

```python
PostgresOperator(
    task_id="insert_log",
    postgres_conn_id="my_postgres",
    sql="INSERT INTO audit_log (event, run_date) VALUES (%s, %s)",
    parameters=("pipeline_run", "2024-01-15"),
)
```

Note: `parameters` uses `%s` (psycopg2 style), NOT `{{ }}` (Jinja style). These are different systems.

---

**Q7. How do you use Jinja templates in PostgresOperator SQL?**

The `sql` parameter is a Jinja template field. You can embed `{{ ds }}`, `{{ run_id }}`, `{{ var.value.x }}`, and other Airflow macros directly:

```python
PostgresOperator(
    task_id="load_daily",
    postgres_conn_id="my_postgres",
    sql="""
        INSERT INTO daily_summary (run_date, total)
        SELECT '{{ ds }}'::DATE, SUM(amount)
        FROM raw_orders
        WHERE order_date = '{{ ds }}';
    """,
)
```

Jinja templates are rendered before the SQL is sent to the database. This is the standard way to make SQL time-aware.

---

**Q8. How do you run multiple SQL statements in one PostgresOperator task?**

Two options:

**Option 1 — List of statements** (each runs in sequence):
```python
PostgresOperator(
    task_id="setup_tables",
    postgres_conn_id="my_postgres",
    sql=[
        "DELETE FROM staging WHERE run_date = '{{ ds }}'",
        "INSERT INTO staging SELECT * FROM raw WHERE date = '{{ ds }}'",
        "UPDATE staging SET processed = TRUE WHERE run_date = '{{ ds }}'",
    ],
)
```

**Option 2 — Single multi-line string** (sent as one statement block):
```python
PostgresOperator(
    task_id="atomic_load",
    postgres_conn_id="my_postgres",
    sql="""
        BEGIN;
        DELETE FROM staging WHERE run_date = '{{ ds }}';
        INSERT INTO staging SELECT * FROM raw WHERE date = '{{ ds }}';
        COMMIT;
    """,
)
```

When using a list, each statement runs in its own execution call but within the same connection.

---

**Q9. What is `autocommit` and when should you use it?**

By default, PostgresOperator wraps all statements in a transaction (autocommit is `False`). Setting `autocommit=True` disables the transaction wrapper and commits each statement immediately.

Use `autocommit=True` for:
- `CREATE INDEX CONCURRENTLY` — cannot run inside a transaction block in PostgreSQL
- `CREATE DATABASE` — also cannot run in a transaction
- `VACUUM` and `ANALYZE` — must run outside transactions

```python
PostgresOperator(
    task_id="create_concurrent_index",
    postgres_conn_id="my_postgres",
    sql="CREATE INDEX CONCURRENTLY idx_orders_date ON orders(order_date);",
    autocommit=True,
)
```

---

**Q10. How do you use a `.sql` file instead of an inline string?**

Put the `.sql` file in a path relative to your DAGs folder and reference it:

```python
PostgresOperator(
    task_id="run_from_file",
    postgres_conn_id="my_postgres",
    sql="sql/create_daily_tables.sql",   # relative to dags/ folder
)
```

The `.sql` file can contain Jinja templates — they are rendered before execution. This is great for keeping complex queries out of your DAG Python code.

---

## Advanced Questions

**Q11. How does PostgresOperator handle transactions? What happens if a multi-statement SQL fails midway?**

When `autocommit=False` (the default), all statements in a single `sql` string are executed within a transaction. If any statement raises an exception, the transaction is rolled back automatically — the database returns to its prior state.

However, when you pass a **list** of statements, each is executed in sequence but the transaction behavior depends on the underlying hook implementation. For guaranteed atomicity across multiple statements, use a single SQL string with explicit `BEGIN; ... COMMIT;` or a PostgreSQL `DO $$ ... $$` block.

For idempotent pipelines, a common pattern is: `DELETE WHERE date = '{{ ds }}'` then `INSERT WHERE date = '{{ ds }}'` — this ensures re-runs produce the same result.

---

**Q12. When should you use PostgresOperator vs PythonOperator + psycopg2 (or PostgresHook)?**

| Scenario | Use |
|---|---|
| Run DDL or DML, no result needed | PostgresOperator |
| Call a stored procedure | PostgresOperator |
| Load from a `.sql` file | PostgresOperator |
| Need to read query results into Python | PythonOperator + PostgresHook |
| Dynamic SQL based on Python logic | PythonOperator + PostgresHook |
| Complex conditional logic around the SQL | PythonOperator + PostgresHook |
| UPSERT with conflict logic in Python | PythonOperator + PostgresHook |

```python
# When you need results back:
def count_and_validate(**context):
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    hook = PostgresHook(postgres_conn_id="my_postgres")
    count = hook.get_first("SELECT COUNT(*) FROM staging WHERE date = %s", (context["ds"],))[0]
    if count == 0:
        raise ValueError(f"No rows for {context['ds']}")
```

---

**Q13. How do you handle large result sets with PostgresOperator?**

PostgresOperator is a fire-and-forget operator — it executes SQL but does **not** return result sets to the DAG. It is designed for statements, not queries.

For large result sets you have several options:
1. **Write results to a file in SQL**: `COPY (SELECT ...) TO '/tmp/output.csv' CSV HEADER;`
2. **Use PostgresHook** in PythonOperator with `get_records()`, `get_pandas_df()`, or `get_df()` for structured result handling
3. **Use a transfer operator** like `PostgresToS3Operator` for large data exports directly to cloud storage

```python
from airflow.providers.postgres.operators.postgres import PostgresOperator

# Use PostgreSQL's COPY for bulk exports
export_task = PostgresOperator(
    task_id="export_to_csv",
    postgres_conn_id="my_postgres",
    sql="COPY (SELECT * FROM orders WHERE date = '{{ ds }}') TO '/tmp/orders_{{ ds_nodash }}.csv' CSV HEADER;",
)
```

---

**Q14. How do you make PostgresOperator tasks idempotent (safe to re-run)?**

Design your SQL so re-running produces the same outcome:

```python
# Pattern: delete-then-insert (idempotent)
PostgresOperator(
    task_id="idempotent_load",
    postgres_conn_id="my_postgres",
    sql=[
        "DELETE FROM daily_sales WHERE sale_date = '{{ ds }}'",
        "INSERT INTO daily_sales SELECT * FROM raw_sales WHERE date = '{{ ds }}'",
    ],
)
```

Other idempotent patterns:
- `CREATE TABLE IF NOT EXISTS` for setup tasks
- `INSERT ... ON CONFLICT DO UPDATE` (UPSERT)
- `TRUNCATE` before reload for full-refresh patterns

---

**Q15. What is the PostgresOperator import path and has it changed across Airflow versions?**

In Airflow 2.x and 3.x with the providers package:
```python
from airflow.providers.postgres.operators.postgres import PostgresOperator
```

In older Airflow 1.x (now deprecated):
```python
from airflow.operators.postgres_operator import PostgresOperator
```

Always use the providers import path in Airflow 2+ — the old path was removed.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [02_PythonOperator](../02_PythonOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [04_S3Operator](../04_S3Operator/Theory.md)
