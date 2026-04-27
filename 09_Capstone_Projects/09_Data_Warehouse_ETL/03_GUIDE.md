# Project 09 — Step-by-Step Guide

> Difficulty: 🟠 Minimal Hints. One hint per step — the rest is yours to design.
> This is the last project before Build Yourself. Prove you can do this with minimal scaffolding.

---

## Step 1 — Design the Star Schema and Write DDL

Design the DDL for all 6 tables: `dim_customer`, `dim_product`, `dim_date`, `dim_region`, `fact_sales`, and your staging tables (`stg_api_raw`, `stg_s3_raw`, `stg_oltp_raw`).

**Your task:** Write a `schema.sql` file with all `CREATE TABLE IF NOT EXISTS` statements. Make sure:
- Every dimension table has a surrogate primary key (`_key SERIAL`) and a natural key (`_id`) with a `UNIQUE` constraint
- `fact_sales` references dimension keys with `FOREIGN KEY` constraints (or skip FK constraints for load performance — a valid real-world choice)
- Staging tables are permissive: `TEXT` columns are fine, no constraints

**Hint:** The SCD Type 1 upsert uses `ON CONFLICT (natural_key) DO UPDATE`. Your dimension tables need the natural key column to have a `UNIQUE` constraint for this to work.

---

## Step 2 — Write Extract Tasks with Dynamic Task Mapping

Define a single `@task` function `extract_source(source: str, **context) -> str` that handles all three sources based on the `source` parameter. Use `expand()` to fan it out.

**Your task:** Implement the three extraction branches:
- `"api"`: call a public REST API (e.g., `https://fakestoreapi.com/products` or a mock) and write results to `stg_api_raw`
- `"s3"`: use `boto3` or `s3fs` to read a CSV from a configurable S3 bucket and write to `stg_s3_raw`  
- `"oltp"`: use `PostgresHook` with `postgres_conn_id="postgres_oltp"` to query the source DB and write to `stg_oltp_raw`

**Hint:** Return the staging table name as a string from each mapped task. Use `expand()` like this:
```python
extracted = extract_source.expand(source=["api", "s3", "oltp"])
```

---

## Step 3 — Write TaskGroups

Wrap related tasks in `TaskGroup` contexts. The goal is visual organization in the Airflow UI — all extract tasks should appear under a single collapsed group.

**Your task:** Create three `TaskGroup` blocks: `extract_group`, `transform_group`, `load_group`. Inside `load_group`, create a nested `TaskGroup` called `dim_loads`.

**Hint:**
```python
from airflow.utils.task_group import TaskGroup

with TaskGroup("extract") as extract_group:
    extracted = extract_source.expand(source=["api", "s3", "oltp"])
```

Set dependencies so `transform_group` waits for all of `extract_group`, and `load_group` waits for all of `transform_group`.

---

## Step 4 — Write Dimension Table Loads (SCD Type 1)

Write one `load_dimension` function that takes `dim_name` as a parameter and handles the SCD1 merge from the clean staging table into the warehouse dimension table.

**Your task:** The function should:
1. Query the clean staging table (`stg_{source}_clean` for the relevant source)
2. Execute the `INSERT ... ON CONFLICT ... DO UPDATE` pattern
3. Handle the mapping from staging column names to dimension column names (they may differ)

**Hint:** Use `PostgresHook.run()` with a parameterized SQL string. The `ON CONFLICT` clause requires the column in conflict to have a `UNIQUE` or `PRIMARY KEY` constraint.

---

## Step 5 — Write the Incremental Fact Table Load

The fact table should be loaded incrementally: delete existing rows for `partition_date = {{ ds }}`, then insert fresh rows from the combined staging data.

**Your task:** Write a `load_fact_sales` task that:
1. Runs `DELETE FROM fact_sales WHERE partition_date = %s` with `context["ds"]`
2. Runs the `INSERT ... SELECT ... JOIN` query that resolves dimension keys
3. All four JOINs must succeed — use `INNER JOIN` so rows with unresolvable dimension keys are dropped (and logged as warnings)

**Hint:** The `{{ ds }}` Jinja variable resolves to the DAG's logical date as `YYYY-MM-DD`. In a `PythonOperator`, access it as `context["ds"]`.

---

## Step 6 — Write the Data Quality Assertion Task

After loading, assert that the data meets minimum quality standards. Do not use an external library — write a simple check using raw SQL.

**Your task:** Write a `data_quality_check` function that:
1. Checks row count for each table: `SELECT COUNT(*) FROM {table}` — raise if zero
2. Checks for null PKs: `SELECT COUNT(*) FROM fact_sales WHERE sale_id IS NULL` — raise if > 0
3. Checks FK integrity (optional): unresolvable keys in fact table
4. Logs results in a structured format

**Hint:** Raise `ValueError(f"Quality check failed: {table} has {count} rows")` to fail the task with a descriptive message. Airflow will mark it red and show the message in the logs.

---

## Step 7 — Schedule and Backfill Test

Configure the DAG to run daily with `catchup=True` and test a backfill.

**Your task:**
1. Set `schedule_interval="0 5 * * *"` and `start_date` to 7 days ago
2. Enable `catchup=True`
3. Run:
   ```bash
   airflow dags backfill data_warehouse_etl \
     --start-date 2024-01-08 \
     --end-date 2024-01-14
   ```
4. Verify that `fact_sales` has distinct `partition_date` values for each day
5. Re-run one day and verify no duplicates are created (row count stays the same)

**Hint:** The `DELETE ... WHERE partition_date = %s` + `INSERT` pattern makes backfill idempotent. This is the correct approach for fact tables without a reliable unique key across all columns.

---

## 📂 Navigation

⬅️ **Prev:** [08 — ML Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [10 — Airflow on Kubernetes](../10_Airflow_on_Kubernetes/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
