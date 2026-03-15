# Airflow + Great Expectations — Interview Q&A

These questions appear in interviews for data engineering roles that involve
data quality, ELT pipelines, and production-grade Airflow usage.

---

## Q1. What is Great Expectations and why would you use it in an Airflow pipeline?

**Answer:**
Great Expectations (GX) is an open-source Python library for validating data quality.
You define "expectations" (assertions about your data), and GX evaluates them
against actual data, producing a detailed pass/fail report.

In an Airflow pipeline it solves the problem of **silent data corruption**: without
validation, bad data (nulls, wrong types, out-of-range values) flows silently
into your data warehouse and corrupts downstream reports.

Typical placement in a pipeline:
```
extract → [GX validate] → branch → load  (if pass)
                              ↓ fail
                          alert + stop   (if fail)
```

This "shift-left" approach catches bad data before it reaches the warehouse, where
it is expensive to fix.

---

## Q2. How do you integrate Great Expectations with Airflow?

**Answer:**
Using the `apache-airflow-providers-great-expectations` provider:

```python
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

validate = GreatExpectationsOperator(
    task_id="validate_orders",
    checkpoint_name="orders_checkpoint",
    data_context_root_dir="/opt/airflow/great_expectations",
    fail_task_on_validation_failure=True,
)
```

The operator:
1. Loads the GX Data Context from `data_context_root_dir`.
2. Runs the named checkpoint.
3. The checkpoint validates the data against an expectation suite.
4. If any expectation fails and `fail_task_on_validation_failure=True`, it raises
   an exception, marking the Airflow task as failed.

---

## Q3. What is an Expectation Suite and how do you create one?

**Answer:**
An Expectation Suite is a named collection of expectations stored as a JSON file.
Create one via the GX Python API or the interactive CLI:

```python
import great_expectations as gx

context = gx.get_context(context_root_dir="/opt/airflow/great_expectations")

suite = context.add_expectation_suite("orders_suite")

# Add expectations
validator = context.get_validator(
    batch_request=...,
    expectation_suite_name="orders_suite",
)
validator.expect_column_values_to_not_be_null("order_id")
validator.expect_column_values_to_be_between("amount", min_value=0)
validator.expect_column_values_to_be_in_set(
    "status", ["pending", "shipped", "delivered", "cancelled"]
)
validator.save_expectation_suite()
```

The suite is saved to `great_expectations/expectations/orders_suite.json`.
Commit this file to version control — it documents your data contract.

---

## Q4. What is the difference between a Checkpoint and running the operator directly?

**Answer:**

| Approach | Description | Best for |
|---|---|---|
| **Checkpoint** | Pre-configured validation config: which suite, which data, which actions | Production; reusable; supports multiple actions |
| **Direct operator call** | Pass suite + data source config directly to the operator | Quick validation; ad-hoc use |

A Checkpoint is more powerful because it can trigger **Actions** on validation results:

```yaml
# checkpoints/orders_checkpoint.yml
action_list:
  - name: store_validation_result
    action: { class_name: StoreValidationResultAction }
  - name: update_data_docs
    action: { class_name: UpdateDataDocsAction }
  - name: send_slack_notification
    action:
      class_name: SlackNotificationAction
      slack_webhook: https://hooks.slack.com/...
      notify_on: failure
```

Running validations through a Checkpoint automatically stores results and updates
Data Docs without any extra Airflow tasks.

---

## Q5. How do you handle validation failures gracefully (without failing the whole DAG)?

**Answer:**
Set `fail_task_on_validation_failure=False` and `return_json_dict=True`:

```python
from airflow.operators.python import BranchPythonOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

validate = GreatExpectationsOperator(
    task_id="validate",
    checkpoint_name="orders_checkpoint",
    data_context_root_dir="/opt/airflow/great_expectations",
    fail_task_on_validation_failure=False,
    return_json_dict=True,              # pushes result dict to XCom
)

def branch_on_validation(**context):
    result = context["ti"].xcom_pull(task_ids="validate")
    if result["success"]:
        return "load_to_warehouse"
    else:
        return "send_alert"

branch = BranchPythonOperator(
    task_id="branch_on_result",
    python_callable=branch_on_validation,
)

validate >> branch >> [load_to_warehouse, send_alert]
```

This lets you implement partial-load strategies: load clean rows and quarantine
bad ones, rather than stopping the entire pipeline.

---

## Q6. What are Data Docs and how do they help?

**Answer:**
Data Docs are auto-generated HTML documentation produced by Great Expectations.
They contain:

- The expectation suite definitions (what you expect)
- Validation results for every run (what actually happened)
- A summary of pass/fail rates over time

They serve as a **data contract** that is always up-to-date. Stakeholders can view
Data Docs without knowing Python or SQL.

In Airflow, the `UpdateDataDocsAction` in a Checkpoint rebuilds Data Docs after
each validation run. You can publish Data Docs to S3 or GCS and serve them as
a static website:

```yaml
data_docs_sites:
  s3_site:
    class_name: SiteBuilder
    store_backend:
      class_name: TupleS3StoreBackend
      bucket: my-data-docs-bucket
      prefix: data_docs/
```

---

## Q7. How does GX Cloud differ from local Great Expectations?

**Answer:**

| Feature | Local GX | GX Cloud |
|---|---|---|
| Config storage | Filesystem (YAML/JSON) | Hosted GX Cloud service |
| Validation history | Local filesystem | Cloud-hosted, persistent |
| Data Docs | Self-hosted | Cloud-hosted UI |
| Collaboration | Manual (Git) | Team sharing built-in |
| Cost | Free | Paid (SaaS) |
| Airflow integration | File-based context | Cloud Data Context |

For most teams starting out, local GX with Git-versioned suite files is sufficient.
GX Cloud makes sense for larger teams that want a shared UI and centralised
validation history without managing the infrastructure.

---

## Q8. What alternatives to Great Expectations exist for data quality in Airflow?

**Answer:**

| Tool | How it integrates with Airflow | Strengths |
|---|---|---|
| **dbt tests** | `DbtTestOperator` or dbt Cloud operator | SQL-native; co-located with transformations |
| **Soda** | `SodaCheckOperator` via `apache-airflow-providers-soda` | YAML-based SodaCL; readable by non-engineers |
| **Pandera** | PythonOperator calling `pandera.validate()` | Strong type inference for Pandas/Spark |
| **Custom SQL asserts** | `SqlCheckOperator` | Zero extra dependencies; simple row count checks |
| **Monte Carlo / Bigeye** | Webhooks or operator SDK | Observability platform; ML-based anomaly detection |

GX is the most feature-complete open-source option. For warehouses (Snowflake,
BigQuery), dbt tests are often a simpler choice because they run inside the
warehouse engine.

---

## Q9. How do you version-control your expectation suites?

**Answer:**
Expectation suites are JSON files stored in `great_expectations/expectations/`.
They should be committed to the same repository as your DAGs:

```
repo/
├── dags/
│   └── orders_pipeline.py
├── great_expectations/
│   ├── great_expectations.yml
│   ├── expectations/
│   │   └── orders_suite.json      ← version controlled
│   └── checkpoints/
│       └── orders_checkpoint.yml  ← version controlled
└── tests/
    └── test_expectations.py
```

Benefits:
- Suite changes go through code review.
- You can diff expectation changes between releases.
- CI can run `great_expectations checkpoint run orders_checkpoint` against
  sample data to validate the suite itself before deployment.

---

## Q10. How do you validate data from different sources (Postgres, S3 Parquet, Pandas)?

**Answer:**
GX uses **Data Connectors** to abstract the data source. Each source type requires
a different execution engine:

```python
# Pandas (in-memory DataFrame)
context.add_datasource(
    "pandas_source",
    class_name="Datasource",
    execution_engine={"class_name": "PandasExecutionEngine"},
    data_connectors={
        "runtime": {
            "class_name": "RuntimeDataConnector",
            "batch_identifiers": ["run_id"],
        }
    },
)

# SQL (Postgres, Snowflake, BigQuery)
context.add_datasource(
    "postgres_source",
    class_name="Datasource",
    execution_engine={
        "class_name": "SqlAlchemyExecutionEngine",
        "connection_string": "postgresql+psycopg2://user:pass@host/db",
    },
    data_connectors={
        "default_inferred": {"class_name": "InferredAssetSqlDataConnector"},
    },
)

# Spark (PySpark DataFrame)
context.add_datasource(
    "spark_source",
    class_name="Datasource",
    execution_engine={"class_name": "SparkDFExecutionEngine"},
    data_connectors={
        "runtime": {"class_name": "RuntimeDataConnector", "batch_identifiers": ["run_id"]},
    },
)
```

In Airflow, the Data Context is initialised once per task run. Each task validates
one batch (one logical unit of data), keeping validation scoped and reproducible.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Spark** | [42_Spark_Integration](../42_Spark_Integration/Theory.md) |
| **Next: KPO Deep Dive** | [44_KubernetesPodOperator_Deep_Dive](../44_KubernetesPodOperator_Deep_Dive/Theory.md) |
