# Airflow + dbt Integration — Cheatsheet

Quick reference for orchestrating dbt runs from Airflow.

---

## Two Approaches at a Glance

| Approach | Best for | Setup effort | Task visibility |
|---|---|---|---|
| **BashOperator** | < 10 models, quick start | Low | DAG-level only |
| **astronomer-cosmos** | 10+ models, production | Medium | Per-model task in UI |

---

## Approach 1 — BashOperator (Minimal)

```python
from airflow.operators.bash import BashOperator

dbt_deps = BashOperator(
    task_id="dbt_deps",
    bash_command="cd /opt/dbt/my_project && dbt deps",
)

dbt_run = BashOperator(
    task_id="dbt_run",
    bash_command="dbt run --project-dir /opt/dbt/my_project --vars '{\"execution_date\": \"{{ ds }}\"}'",
)

dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command="dbt test --project-dir /opt/dbt/my_project",
)

dbt_deps >> dbt_run >> dbt_test
```

---

## Approach 2 — astronomer-cosmos (Production)

**Install:**
```bash
pip install astronomer-cosmos[dbt-postgres]
# or: [dbt-bigquery], [dbt-snowflake]
```

**Full DAG factory:**
```python
from cosmos import DbtDag, ProjectConfig, ProfileConfig, ExecutionConfig
from cosmos.profiles import PostgresUserPasswordProfileMapping
from pathlib import Path

dbt_dag = DbtDag(
    dag_id="dbt_cosmos_pipeline",
    schedule="@daily",
    project_config=ProjectConfig(dbt_project_path=Path("/opt/airflow/dbt/my_project")),
    profile_config=ProfileConfig(
        profile_name="my_project",
        target_name="prod",
        profile_mapping=PostgresUserPasswordProfileMapping(conn_id="postgres_warehouse"),
    ),
    execution_config=ExecutionConfig(dbt_executable_path="/usr/local/bin/dbt"),
)
```

**Embedded in a larger pipeline:**
```python
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig

with DAG(...) as dag:
    extract = extract_task()

    transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=ProjectConfig(dbt_project_path=Path("/opt/airflow/dbt/my_project")),
        profile_config=profile_config,
    )

    load = load_task()

    extract >> transform >> load
```

---

## Passing Variables to dbt

```python
# Pass Airflow execution date to dbt
BashOperator(
    task_id="dbt_run",
    bash_command="dbt run --vars '{\"execution_date\": \"{{ ds }}\", \"schema\": \"prod\"}'",
)
```

```sql
-- In your dbt model
WHERE order_date = '{{ var("execution_date") }}'
```

---

## Handling dbt Test Failures

```python
# Soft-fail pattern: capture failure, alert, but continue pipeline
dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command="dbt test --store-failures 2>&1 | tee /tmp/dbt_output.txt; exit ${PIPESTATUS[0]}",
    trigger_rule="all_done",
)

@task(trigger_rule="one_failed")
def alert_on_failure():
    # Read /tmp/dbt_output.txt and send Slack/email
    pass
```

---

## Best Practices

| Do | Why |
|---|---|
| Use cosmos for 10+ models | Per-model retries + full lineage visibility |
| Always run `dbt test` after `dbt run` | Catch bad data before downstream consumers see it |
| Pass `execution_date` as a dbt var | Idempotent backfills |
| Store dbt profiles in Airflow connections | No credentials in code |
| Use `--select` for incremental runs | Faster for large dbt projects |
| Enable `--store-failures` in production | Failing rows saved to DB for debugging |

---

## dbt Command Reference

```bash
dbt deps                          # Install packages (run first)
dbt run                           # Run all models
dbt run --select +my_model        # Run model + all upstream
dbt run --select my_model+        # Run model + all downstream
dbt test                          # Run all tests
dbt test --select my_model        # Test one model
dbt run --vars '{"key": "val"}'   # Pass variables
dbt run --profiles-dir /path      # Custom profiles location
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Example** | [Code_Example.md](./Code_Example.md) |
| **Next: Spark** | [42_Spark_Integration/Theory.md](../42_Spark_Integration/Theory.md) |
| **Parent: Integrations** | [Readme.md](../Readme.md) |
