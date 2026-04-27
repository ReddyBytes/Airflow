# 29 — DAG Patterns and Best Practices

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Idempotency](#1-idempotency) · [Avoid Top-Level Code](#4-avoid-top-level-code) · [Backfill Safety](#3-backfill-safety)

**Should Learn** — important for real projects and interviews:
[Atomic Writes](#2-atomic-writes) · [DAG Factory Pattern](#5-dag-factory-pattern) · [Fan-Out Fan-In](#6-fan-out--fan-in-pattern)

**Good to Know** — useful in specific situations, not needed daily:
[Config-Driven DAGs](#7-config-driven-dags-yamljson) · [DAG Documentation](#9-documentation-in-dags)

**Reference** — skim once, look up when needed:
[DAG Versioning Strategies](#8-dag-versioning)

---

## The Story

After years of running Airflow in production, certain patterns emerge as reliable and others as maintenance nightmares. The team that treats Airflow DAGs as casual scripts ends up with pipelines that break mysteriously on reruns, fail non-reproducibly, and resist debugging. The team that applies these patterns ends up with pipelines that can be retried confidently, backfilled safely, and understood by anyone who reads the code.

---

## 1. Idempotency

**The most important principle in Airflow DAG design.**

An idempotent task produces the same result whether run once or ten times. Running it again doesn't create duplicates, doesn't corrupt data, and doesn't fail because the previous run already wrote the output.

### Non-Idempotent (Dangerous)
```python
# DANGEROUS: Appends data. Running twice = duplicate rows.
def load_orders():
    df = fetch_orders_for_today()
    df.to_sql("orders", engine, if_exists="append")   # Appends!
```

### Idempotent (Correct)
```python
# SAFE: Replace pattern. Running twice = same result.
def load_orders(**context):
    ds = context["ds"]
    df = fetch_orders_for_date(ds)
    # Delete existing data for this date, then insert
    engine.execute(f"DELETE FROM orders WHERE order_date = '{ds}'")
    df.to_sql("orders", engine, if_exists="append")
```

Or use upsert (INSERT ... ON CONFLICT DO UPDATE):
```python
def load_orders(**context):
    ds = context["ds"]
    df = fetch_orders_for_date(ds)
    # PostgreSQL upsert — running twice is identical
    df.to_sql("orders_staging", engine, if_exists="replace")
    engine.execute("""
        INSERT INTO orders SELECT * FROM orders_staging
        ON CONFLICT (order_id) DO UPDATE SET
            amount = EXCLUDED.amount,
            status = EXCLUDED.status
    """)
```

---

## 2. Atomic Writes

Write to a temporary location first, then rename on success. This prevents downstream consumers from seeing partial data.

```python
# BAD: Downstream reads partial file if task dies mid-write
def write_data():
    with open("/data/output/report.csv", "w") as f:
        for chunk in generate_large_dataset():
            f.write(chunk)   # If this crashes at 50%, partial file remains

# GOOD: Atomic write — either the complete file exists or nothing
def write_data():
    import tempfile
    import os

    output_path = "/data/output/report.csv"
    tmp_path = f"{output_path}.tmp.{os.getpid()}"

    with open(tmp_path, "w") as f:
        for chunk in generate_large_dataset():
            f.write(chunk)

    # Rename is atomic on POSIX filesystems
    os.replace(tmp_path, output_path)
    # If we crash before this line, the .tmp file is ignored
    # Downstream consumers never see a partial file
```

For S3/GCS:
```python
# S3 multipart upload is atomic by design — object only appears when upload completes
s3.upload_file("local_output.csv", bucket, "output/report.csv")
# Alternatively: write to a temp key, then copy to final key
s3.copy_object(
    CopySource={"Bucket": bucket, "Key": "output/report.csv.tmp"},
    Bucket=bucket,
    Key="output/report.csv",
)
s3.delete_object(Bucket=bucket, Key="output/report.csv.tmp")
```

---

## 3. Backfill Safety

Design every task to be safely re-run for historical dates. This means:
- Use `{{ ds }}` or `{{ logical_date }}` in all queries — never `datetime.now()`
- Don't use `datetime.today()` to determine what data to process
- Never append based on "current time" — always partition by logical date

```python
# BAD: Cannot be backfilled
def extract():
    today = datetime.now()   # Always processes today's data
    return fetch_data(today)

# GOOD: Backfillable
def extract(**context):
    logical_date = context["logical_date"]
    return fetch_data(logical_date.date())   # Uses scheduled execution date
```

---

## 4. Avoid Top-Level Code

Any code outside a function or class runs when Airflow parses the DAG file — which happens every `min_file_process_interval` seconds.

```python
# BAD patterns at module level:
import pandas                         # Slow import
from my_module import complex_init    # Runs on every parse
conn = get_db_connection()            # DB call on every parse
config = Variable.get("my_config")   # Airflow API call on every parse
TABLES = fetch_tables_from_db()      # DB query on every parse

# GOOD: Only static definitions at module level
from datetime import datetime
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator

TABLES = ["orders", "customers"]    # Static list, no DB call

def process_table(table: str):
    import pandas as pd              # Heavy import inside function
    config = Variable.get("config")  # API call inside function
    ...

with DAG(...) as dag:
    for table in TABLES:
        PythonOperator(task_id=f"process_{table}", python_callable=process_table, op_kwargs={"table": table})
```

---

## 5. DAG Factory Pattern

Generate many similar DAGs from a config — one file, zero duplication.

```python
# dags/etl_factory.py
"""
Generates one ETL DAG per table defined in DAG_CONFIGS.
Adding a new table: add one entry to DAG_CONFIGS. No new file needed.
"""
from __future__ import annotations

from datetime import datetime

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

# Config lives here — could also be read from a YAML file
DAG_CONFIGS = [
    {
        "table": "orders",
        "source_conn": "postgres_source",
        "dest_conn": "postgres_warehouse",
        "schedule": "0 6 * * *",     # 6 AM daily
        "partition_column": "order_date",
    },
    {
        "table": "customers",
        "source_conn": "postgres_source",
        "dest_conn": "postgres_warehouse",
        "schedule": "0 7 * * *",     # 7 AM daily
        "partition_column": "created_at",
    },
    {
        "table": "products",
        "source_conn": "postgres_source",
        "dest_conn": "postgres_warehouse",
        "schedule": "0 5 * * 0",     # Sunday 5 AM weekly
        "partition_column": "updated_at",
    },
]


def make_etl_dag(config: dict) -> DAG:
    """Build and return a DAG for the given table config."""
    table = config["table"]
    partition_col = config["partition_column"]

    with DAG(
        dag_id=f"etl_{table}",
        description=f"Extract and load {table} table",
        schedule=config["schedule"],
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["etl", table],
        default_args={
            "retries": 2,
            "depends_on_past": False,
        },
        doc_md=f"""
        ## ETL: {table}

        Incremental load from source PostgreSQL to warehouse.
        Partitioned by `{partition_col}`.

        **Source:** `{config['source_conn']}`
        **Destination:** `{config['dest_conn']}`
        """,
    ) as dag:

        extract = SQLExecuteQueryOperator(
            task_id="extract",
            conn_id=config["source_conn"],
            sql=f"""
                SELECT * FROM {table}
                WHERE {partition_col}::date = '{{{{ ds }}}}'
            """,
        )

        load = SQLExecuteQueryOperator(
            task_id="load",
            conn_id=config["dest_conn"],
            sql=f"""
                DELETE FROM {table}
                WHERE {partition_col}::date = '{{{{ ds }}}}';

                INSERT INTO {table}
                SELECT * FROM {table}_staging;
            """,
        )

        validate = SQLExecuteQueryOperator(
            task_id="validate",
            conn_id=config["dest_conn"],
            sql=f"""
                SELECT COUNT(*) FROM {table}
                WHERE {partition_col}::date = '{{{{ ds }}}}'
                HAVING COUNT(*) = 0;
            """,
        )

        extract >> load >> validate

    return dag


# Register all generated DAGs in module globals — Airflow discovers them here
for _config in DAG_CONFIGS:
    _dag = make_etl_dag(_config)
    globals()[_dag.dag_id] = _dag
```

---

## 6. Fan-Out / Fan-In Pattern

Process items in parallel, then aggregate results.

```python
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

REGIONS = ["us-east", "us-west", "eu-central", "ap-southeast"]

with DAG("regional_report", schedule="@daily", start_date=datetime(2026, 1, 1)) as dag:

    start = PythonOperator(task_id="start", python_callable=lambda: print("starting"))

    # Fan-out: one task per region (runs in parallel)
    region_tasks = []
    for region in REGIONS:
        t = PythonOperator(
            task_id=f"process_{region.replace('-', '_')}",
            python_callable=lambda r=region: process_region(r),
        )
        start >> t
        region_tasks.append(t)

    # Fan-in: aggregate after all regions complete
    aggregate = PythonOperator(
        task_id="aggregate_all_regions",
        python_callable=aggregate_results,
        trigger_rule="all_success",  # Only run if ALL fan-out tasks succeeded
    )

    for t in region_tasks:
        t >> aggregate
```

Modern approach using Dynamic Task Mapping:
```python
def process_region(region: str):
    return do_work(region)

def aggregate(results: list):
    return sum(results)

with DAG(...) as dag:
    process = PythonOperator.partial(
        task_id="process",
        python_callable=process_region,
    ).expand(op_args=[[r] for r in REGIONS])

    PythonOperator(
        task_id="aggregate",
        python_callable=aggregate,
        op_args=[process.output],  # XCom from all mapped tasks
    )
```

---

## 7. Config-Driven DAGs (YAML/JSON)

For large teams, define DAG configurations in YAML files rather than Python:

```yaml
# config/etl_tables.yaml
tables:
  - name: orders
    source: postgres_source
    schedule: "0 6 * * *"
    partition_col: order_date
    tags: [etl, orders, critical]

  - name: inventory
    source: postgres_source
    schedule: "0 4 * * *"
    partition_col: updated_at
    tags: [etl, inventory]
```

```python
# dags/yaml_factory.py
import yaml
from pathlib import Path

config_path = Path(__file__).parent.parent / "config" / "etl_tables.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

for table_config in config["tables"]:
    dag = make_etl_dag(table_config)
    globals()[dag.dag_id] = dag
```

---

## 8. DAG Versioning

Strategies for managing DAG changes without breaking running instances:

```python
# Option 1: Version suffix in dag_id
# When making breaking changes, create a new DAG with a version suffix
# Old: etl_orders
# New: etl_orders_v2
with DAG(dag_id="etl_orders_v2", ...):
    ...

# Option 2: Deprecation via params and tags
with DAG(
    dag_id="etl_orders",
    tags=["deprecated", "use_etl_orders_v2"],
    is_paused_upon_creation=True,
):
    ...

# Option 3: Semantic versioning in description/docs
with DAG(
    dag_id="etl_orders",
    description="[v2.1.0] Orders ETL pipeline. Changed: added validation step.",
    doc_md="""
    ## Changelog
    - v2.1.0 (2026-03-15): Added data validation step
    - v2.0.0 (2026-01-01): Migrated to dbt for transformations
    - v1.0.0 (2025-06-01): Initial version
    """,
):
    ...
```

---

## 9. Documentation in DAGs

Well-documented DAGs are self-service — team members can understand and debug without hunting down the original author.

```python
with DAG(
    dag_id="payments_reconciliation",
    doc_md="""
    ## Payments Reconciliation

    Reconciles payment records between the payments service and the ledger.

    **Runs:** Daily at 6 AM UTC
    **Owner:** payments-platform team
    **Slack:** #payments-data-oncall
    **Runbook:** https://wiki.corp.com/airflow/payments_reconciliation

    ### What it does:
    1. Extracts transactions from payments service API
    2. Joins with ledger records from PostgreSQL
    3. Identifies discrepancies and writes to `audit.reconciliation_exceptions`
    4. Sends a summary to #finance-ops Slack channel

    ### When it fails:
    - Payments API down: retry automatically (3x). Notify #payments-oncall after 3 failures.
    - Ledger discrepancies > threshold: intentional FAIL. Review exceptions table.
    """,
) as dag:

    extract = PythonOperator(
        task_id="extract_payments",
        python_callable=extract_payments,
        doc_md="""
        Fetches all transactions from the Payments API for `{{ ds }}`.

        Output: list of transaction dicts pushed to XCom under key `transactions`.
        Expects connection `payments_api_default` to be configured.
        """,
    )
```

---

## Key Takeaways

- Idempotency is non-negotiable: every task must produce identical results when run multiple times
- Atomic writes prevent downstream consumers from seeing partial data
- Use `{{ ds }}` / `{{ logical_date }}` everywhere — never `datetime.now()`
- No `Variable.get()`, no heavy imports, no DB calls at module level
- DAG factory pattern: one Python file generates N DAGs — reduces maintenance, reduces parse time
- Fan-out / fan-in with `trigger_rule="all_success"` is the standard parallel pattern
- Document every DAG with `doc_md` — include ownership, runbook links, failure guidance
- Version DAGs with a `_v2` suffix when making breaking changes — never modify a running DAG's logic in place
