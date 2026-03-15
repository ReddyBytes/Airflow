# 04 — Operators: Cheatsheet

## All Major Operators — Quick Reference

| Operator | Package | Use Case |
|---|---|---|
| `BashOperator` | `airflow.operators.bash` | Run shell/bash commands |
| `PythonOperator` | `airflow.operators.python` | Run a Python function |
| `EmptyOperator` | `airflow.operators.empty` | Placeholder / no-op task |
| `BranchPythonOperator` | `airflow.operators.python` | Conditional branching |
| `LatestOnlyOperator` | `airflow.operators.latest_only` | Skip if not latest run |
| `TriggerDagRunOperator` | `airflow.operators.trigger_dagrun` | Trigger another DAG |
| `EmailOperator` | `airflow.operators.email` | Send email |
| `PostgresOperator` | `airflow.providers.postgres.operators.postgres` | Run SQL on PostgreSQL |
| `MySqlOperator` | `airflow.providers.mysql.operators.mysql` | Run SQL on MySQL |
| `BigQueryOperator` | `airflow.providers.google.cloud.operators.bigquery` | Run SQL on BigQuery |
| `LocalFilesystemToS3Operator` | `airflow.providers.amazon.aws.transfers.local_to_s3` | Upload file to S3 |
| `S3ToRedshiftOperator` | `airflow.providers.amazon.aws.transfers.s3_to_redshift` | Copy S3 to Redshift |
| `S3CopyObjectOperator` | `airflow.providers.amazon.aws.operators.s3` | Copy S3 object |
| `HttpOperator` | `airflow.providers.http.operators.http` | Make HTTP request |
| `DockerOperator` | `airflow.providers.docker.operators.docker` | Run Docker container |
| `KubernetesPodOperator` | `airflow.providers.cncf.kubernetes.operators.pod` | Run task in K8s pod |
| `SparkSubmitOperator` | `airflow.providers.apache.spark.operators.spark_submit` | Submit Spark job |
| `SFTPOperator` | `airflow.providers.sftp.operators.sftp` | Transfer via SFTP |

---

## BaseOperator Parameters Cheatsheet

These parameters work on **every** operator:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | str | required | Unique task identifier within the DAG |
| `dag` | DAG | required | The DAG this task belongs to |
| `retries` | int | `0` | Number of times to retry on failure |
| `retry_delay` | timedelta | `5 min` | Time to wait between retries |
| `retry_exponential_backoff` | bool | `False` | Exponential backoff between retries |
| `max_retry_delay` | timedelta | `None` | Cap on retry delay |
| `execution_timeout` | timedelta | `None` | Kill task if it exceeds this duration |
| `depends_on_past` | bool | `False` | Previous run must succeed first |
| `wait_for_downstream` | bool | `False` | All downstream tasks of prev run must succeed |
| `email` | str/list | `None` | Email(s) for alerts |
| `email_on_failure` | bool | `True` | Send email on failure |
| `email_on_retry` | bool | `True` | Send email on retry |
| `on_failure_callback` | callable | `None` | Python function to call on failure |
| `on_success_callback` | callable | `None` | Python function to call on success |
| `on_retry_callback` | callable | `None` | Python function to call on retry |
| `pool` | str | `default_pool` | Resource pool name |
| `pool_slots` | int | `1` | Slots this task occupies in the pool |
| `priority_weight` | int | `1` | Scheduling priority (higher = sooner) |
| `trigger_rule` | str | `all_success` | When to trigger this task |
| `start_date` | datetime | `None` | Earliest this task can be scheduled |
| `end_date` | datetime | `None` | Latest this task can be scheduled |
| `run_as_user` | str | `None` | Unix user to impersonate |
| `queue` | str | `default` | Celery queue name |

---

## Operator Type Comparison

| Category | Does What | Examples | Blocks Pipeline? |
|---|---|---|---|
| Action | Executes a job | Bash, Python, SQL operators | No (runs then finishes) |
| Transfer | Moves data | S3, SFTP, GCS transfer operators | No (runs then finishes) |
| Sensor | Waits for condition | File, HTTP, ExternalTask sensors | Yes (holds until condition met) |
| Utility | Controls flow | Branch, Trigger, Empty operators | Sometimes (branch skips paths) |

---

## Trigger Rules Cheatsheet

The `trigger_rule` parameter controls when a task runs based on its upstream tasks:

| Rule | Meaning |
|---|---|
| `all_success` | All upstream tasks succeeded (default) |
| `all_failed` | All upstream tasks failed |
| `all_done` | All upstream tasks are done (any state) |
| `one_success` | At least one upstream task succeeded |
| `one_failed` | At least one upstream task failed |
| `none_failed` | No upstream task failed (success or skipped is OK) |
| `none_skipped` | No upstream task was skipped |
| `always` | Run regardless of upstream state |

---

## When to Use Which Operator — Decision Guide

```
What do you need to do?
│
├── Run a shell command or CLI tool? ──────────────────► BashOperator
│
├── Run Python logic? ─────────────────────────────────► PythonOperator
│
├── Choose between paths based on logic? ──────────────► BranchPythonOperator
│
├── Wait for something?
│   ├── A file to appear? ──────────────────────────── FileSensor
│   ├── An API to be ready? ────────────────────────── HttpSensor
│   └── Another DAG to finish? ─────────────────────── ExternalTaskSensor
│
├── Talk to a database?
│   ├── PostgreSQL? ────────────────────────────────── PostgresOperator
│   ├── MySQL? ─────────────────────────────────────── MySqlOperator
│   └── BigQuery? ──────────────────────────────────── BigQueryOperator
│
├── Move files?
│   ├── Local → S3? ────────────────────────────────── LocalFilesystemToS3Operator
│   ├── S3 → Redshift? ─────────────────────────────── S3ToRedshiftOperator
│   └── Via SFTP? ──────────────────────────────────── SFTPOperator
│
├── Trigger another DAG? ───────────────────────────────► TriggerDagRunOperator
│
├── Send a notification? ───────────────────────────────► EmailOperator
│
├── Run in a container? ────────────────────────────────► DockerOperator / KubernetesPodOperator
│
└── Mark start/end or group tasks? ────────────────────► EmptyOperator
```

---

## Common Import Paths

```python
# Core operators (no extra install needed)
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.email import EmailOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.latest_only import LatestOnlyOperator

# Providers (install: apache-airflow-providers-postgres)
from airflow.providers.postgres.operators.postgres import PostgresOperator

# Providers (install: apache-airflow-providers-amazon)
from airflow.providers.amazon.aws.operators.s3 import S3CreateBucketOperator
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator

# Providers (install: apache-airflow-providers-http)
from airflow.providers.http.operators.http import SimpleHttpOperator

# Providers (install: apache-airflow-providers-docker)
from airflow.providers.docker.operators.docker import DockerOperator
```
