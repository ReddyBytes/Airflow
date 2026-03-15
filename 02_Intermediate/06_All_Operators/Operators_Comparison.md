# 04 — Operators Comparison

A side-by-side reference for the most commonly used operators in Airflow.

---

## Operators Comparison Table

| Operator | Use Case | Package | Key Parameters | Pros | Cons | When to Use |
|---|---|---|---|---|---|---|
| `BashOperator` | Run shell commands, scripts, CLI tools | `airflow.operators.bash` | `bash_command`, `env`, `cwd` | Simple, versatile, no extra install | Harder to test, shell injection risk | Quick shell tasks, CLI wrappers, legacy scripts |
| `PythonOperator` | Run any Python function | `airflow.operators.python` | `python_callable`, `op_kwargs`, `op_args` | Full Python power, easy to test | Heavy functions can slow down workers | Business logic, API calls, data transforms |
| `PostgresOperator` | Run SQL on PostgreSQL | `airflow.providers.postgres` | `sql`, `postgres_conn_id`, `parameters` | Clean SQL execution, supports templates | Requires connection setup, only PostgreSQL | DB operations, table creation, ETL loads |
| `LocalFilesystemToS3Operator` | Upload local file to S3 | `airflow.providers.amazon.aws` | `filename`, `dest_key`, `dest_bucket`, `aws_conn_id` | Simple, handles multipart upload | AWS-specific, requires IAM setup | Archiving outputs, pushing reports to S3 |
| `S3CopyObjectOperator` | Copy S3 object between buckets/keys | `airflow.providers.amazon.aws` | `source_bucket_key`, `dest_bucket_key` | No local disk needed | AWS-specific | S3-to-S3 data movement |
| `EmailOperator` | Send email notifications | `airflow.operators.email` | `to`, `subject`, `html_content` | Built-in, easy alerting | Requires SMTP setup, limited formatting | Alerts, reports, pipeline summaries |
| `TriggerDagRunOperator` | Trigger another DAG | `airflow.operators.trigger_dagrun` | `trigger_dag_id`, `conf`, `wait_for_completion` | Enables modular pipelines | Creates tight coupling between DAGs | Master/sub-pipeline patterns, fan-out workflows |
| `BranchPythonOperator` | Conditional branching based on logic | `airflow.operators.python` | `python_callable` (returns task_id) | Flexible routing logic | Branches not taken are marked Skipped | A/B paths, environment-specific logic |
| `EmptyOperator` | Placeholder, group start/end | `airflow.operators.empty` | `task_id` only | Zero overhead, great for structure | Does nothing by itself | Pipeline entry/exit points, grouping |

---

## Key Parameters Deep-Dive

### BashOperator
```python
BashOperator(
    task_id="run_script",
    bash_command="python /opt/scripts/process.py",
    env={"MY_VAR": "value"},         # Extra env vars (merged with system env)
    cwd="/opt/data",                  # Working directory
    output_encoding="utf-8",          # Encoding for captured output
    skip_exit_code=None,              # Exit code that means "skip" not "fail"
)
```

### PythonOperator
```python
PythonOperator(
    task_id="run_function",
    python_callable=my_function,
    op_args=[arg1, arg2],             # Positional arguments
    op_kwargs={"key": "value"},       # Keyword arguments
)
```

### PostgresOperator
```python
PostgresOperator(
    task_id="run_sql",
    postgres_conn_id="my_postgres",   # Connection ID from Airflow UI
    sql="INSERT INTO table VALUES (%s)",
    parameters=("value",),            # Bind parameters (prevents SQL injection)
    autocommit=False,                 # Wrap in transaction?
)
```

### TriggerDagRunOperator
```python
TriggerDagRunOperator(
    task_id="trigger_child",
    trigger_dag_id="child_dag_id",
    conf={"param": "value"},          # Pass data to the triggered DAG
    wait_for_completion=True,         # Block until triggered DAG finishes
    reset_dag_run=True,               # Re-run if already exists
    poke_interval=30,                 # How often to check status (seconds)
)
```

### BranchPythonOperator
```python
def choose_branch(**context):
    if condition:
        return "task_a"               # Return task_id of branch to follow
    return "task_b"

BranchPythonOperator(
    task_id="decide",
    python_callable=choose_branch,
)
```

---

## Operator Selection Summary

```
Need to...                          → Use
─────────────────────────────────────────────────────────────────
Run a shell command                 → BashOperator
Run Python code                     → PythonOperator
Execute SQL on Postgres             → PostgresOperator
Upload to S3                        → LocalFilesystemToS3Operator
Copy within S3                      → S3CopyObjectOperator
Send an email                       → EmailOperator
Trigger another DAG                 → TriggerDagRunOperator
Pick a branch                       → BranchPythonOperator
Mark start/end of group             → EmptyOperator
Wait for file/API/DAG               → Sensor (see 05_Sensors)
```

---

## Provider Installation Reference

| Operator Group | pip install command |
|---|---|
| Core (Bash, Python, Email) | Included with `apache-airflow` |
| PostgreSQL | `pip install apache-airflow-providers-postgres` |
| AWS / S3 | `pip install apache-airflow-providers-amazon` |
| Google Cloud | `pip install apache-airflow-providers-google` |
| HTTP | `pip install apache-airflow-providers-http` |
| Docker | `pip install apache-airflow-providers-docker` |
| Kubernetes | `pip install apache-airflow-providers-cncf-kubernetes` |
| Spark | `pip install apache-airflow-providers-apache-spark` |
| SFTP/SSH | `pip install apache-airflow-providers-sftp` |
