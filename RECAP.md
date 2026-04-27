# Airflow Mastery — Topic Recap

> One-line summary of every module across all 8 sections. Use this to quickly review what each concept covers before diving deeper.

---

## 00 — Learning Guide

| Topic | Summary |
|---|---|
| How to Use This Repo | Navigation guide, learning tracks, and how to find the right starting point |
| Learning Paths | Beginner / intermediate / advanced / expert progression with time estimates |
| Progress Tracker | Personal checklist to mark completed modules |

---

## 01 — Beginner

| Topic | Summary |
|---|---|
| What is Airflow | Workflow orchestration — what it is, what problem it solves, key terminology |
| Architecture | Scheduler, executor, worker, webserver, metadata DB — how they work together |
| Installation | Local setup, Docker Compose, virtual environment, first run |
| First DAG | Writing a minimal DAG — dag definition, task, schedule, basic operators |
| BashOperator | Execute shell commands from DAG tasks |
| PythonOperator | Call Python callables as DAG tasks |
| EmailOperator | Send notification emails from pipelines |

---

## 02 — Intermediate

| Topic | Summary |
|---|---|
| All Core Operators | FileSensor, HttpOperator, BranchPythonOperator and more |
| Sensors | Wait for external conditions — FileSensor, HttpSensor, S3KeySensor |
| Executors | LocalExecutor, CeleryExecutor, KubernetesExecutor — when to use each |
| Connections | Storing credentials — conn_id, UI config, environment variable override |
| Variables | Airflow Variables for runtime config — UI, CLI, and Python access |
| XComs | Cross-task communication — push, pull, limits, and best practices |
| TaskFlow API | @task decorator — modern Pythonic DAG authoring, automatic XCom handling |
| Jinja Templates | Parameterize SQL, commands, and paths with execution date macros |

---

## 03 — Advanced

| Topic | Summary |
|---|---|
| Branching | BranchPythonOperator — conditional task execution paths |
| Task Groups | Visual and logical grouping of related tasks in the UI |
| Dynamic Task Mapping | .expand() and .partial() — generate tasks at runtime from a list |
| Deferrable Operators | Async operators that release worker while waiting — Triggerer component |
| Callbacks | on_success_callback, on_failure_callback, sla_miss_callback |
| Pools | Slot-based resource limiting — control concurrency for heavy tasks |
| Monitoring | Airflow metrics, Prometheus integration, task duration tracking |
| Testing DAGs | pytest, DAG validation, task-level unit tests, integration testing |
| Custom Timetables | Beyond cron — data-interval-aware schedules, irregular frequencies |

---

## 04 — Expert

| Topic | Summary |
|---|---|
| Plugins | Extending Airflow — custom operators, hooks, macros, views |
| Custom Operators | Writing reusable BaseOperator subclasses with proper __init__ and execute |
| Custom Hooks | Wrapping external systems into reusable BaseHook subclasses |
| Secrets Backends | HashiCorp Vault, AWS Secrets Manager — external credential management |
| REST API | Triggering DAGs, querying runs, managing variables via Airflow REST API |
| Performance Optimization | DAG parsing time, scheduler tuning, worker pool sizing |
| Remote Logging | S3, GCS, Azure Blob — pushing task logs to cloud storage |
| DAG Patterns | Taskflow best practices, idempotent tasks, atomic operations |

---

## 05 — Airflow 3 Features

| Topic | Summary |
|---|---|
| What's New in Airflow 3 | Breaking changes, migration guide, new architecture decisions |
| Asset-Driven Scheduling | Dataset → Asset rename, schedule DAGs to run when assets are updated |
| DAG Versioning | Track DAG changes, historical execution with old DAG version |
| Auth Manager | Pluggable authentication — FAB, Kerberos, custom auth managers |
| Edge Executor | Distributed task execution to remote edge workers |
| Event-Driven Scheduling | Trigger DAGs from external events beyond cron or dataset updates |
| Object Storage | Abstracted file operations across S3, GCS, Azure Blob via unified API |

---

## 06 — Airflow on Cloud

| Topic | Summary |
|---|---|
| Cloud Deployment Overview | Managed vs self-hosted, cost considerations, scaling strategies |
| AWS EKS | Self-managed Airflow on Kubernetes — KubernetesExecutor, Helm chart, IRSA |
| AWS MWAA | Managed Workflows for Apache Airflow — setup, scaling, plugins, limitations |
| GCP Cloud Composer | Google's managed Airflow — environment tiers, PyPI packages, DAG sync |

---

## 07 — Integrations

| Topic | Summary |
|---|---|
| dbt Integration | Run dbt models from Airflow — DbtCloudOperator, local dbt execution |
| Spark Integration | SparkSubmitOperator, LivyOperator — trigger Spark jobs from DAGs |
| Great Expectations | Data quality gates — validate DataFrames, fail tasks on schema violations |
| KubernetesPodOperator | Run any Docker container as a task — isolation, resource limits, secrets |

---

## 08 — Projects

| Project | Summary |
|---|---|
| Forex ETL Pipeline | Fetch currency rates API → transform → load to Postgres (beginner) |
| File Processing Pipeline | Watch S3 for new files → process → archive (beginner) |
| Data Quality Gate | Run Great Expectations checks as pipeline stage (intermediate) |
| Multi-Source ETL | Pull from 3 APIs, join, deduplicate, load to data warehouse (intermediate) |
| ML Training Pipeline | Feature engineering → train → evaluate → register model (advanced) |
| Multi-Cloud ETL | AWS S3 → GCP BigQuery cross-cloud pipeline with failover (advanced) |

---

*Total sections: 8 · Last updated: 2026-04-21*
