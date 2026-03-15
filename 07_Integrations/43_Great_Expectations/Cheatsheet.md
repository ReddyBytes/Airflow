# Airflow + Great Expectations — Cheatsheet

Great Expectations (GX) is a data quality framework that lets you define
"expectations" about your data (e.g., "column `age` is never negative") and
validate DataFrames or tables against them. In Airflow pipelines, you run GX
checks as tasks — typically after extracting data and before loading it.

---

## Provider Package

```bash
pip install apache-airflow-providers-great-expectations
# Also need the core GX library
pip install great-expectations>=0.18
```

---

## Core GX Concepts for Airflow Integration

| Concept | Description |
|---|---|
| **Data Context** | Top-level GX object; points to config, suites, checkpoints |
| **Expectation Suite** | A named collection of expectations for a dataset |
| **Batch** | A slice of data to validate (a DataFrame, SQL query, or file) |
| **Checkpoint** | Combines suite + batch config + action list (e.g., notify on failure) |
| **Validation Result** | Pass/fail per expectation + overall pass/fail |
| **Data Docs** | HTML documentation auto-generated from validation results |

---

## GreatExpectationsOperator — Key Parameters

```python
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

GreatExpectationsOperator(
    task_id="validate_orders",

    # Option A: run a named checkpoint (recommended)
    checkpoint_name="orders_checkpoint",
    data_context_root_dir="/opt/airflow/great_expectations",

    # Option B: run a suite directly against a Pandas DF (via conn)
    # expectation_suite_name="orders_suite",
    # data_asset_name="orders_df",

    # Fail the task if any expectation fails (default True)
    fail_task_on_validation_failure=True,

    # Return validation results to XCom (useful for branching)
    return_json_dict=True,

    conn_id="my_db_conn",                   # used when validating SQL source
    schema="public",
    table="orders",
)
```

---

## File Layout

```
great_expectations/
├── great_expectations.yml          # Data Context config
├── expectations/
│   └── orders_suite.json           # Expectation suite
├── checkpoints/
│   └── orders_checkpoint.yml       # Checkpoint config
└── uncommitted/
    └── data_docs/
        └── local_site/             # Generated HTML docs
```

---

## great_expectations.yml (minimal)

```yaml
config_version: 3

datasources:
  my_postgres:
    class_name: Datasource
    module_name: great_expectations.datasource
    execution_engine:
      class_name: SqlAlchemyExecutionEngine
      connection_string: postgresql+psycopg2://user:pass@host:5432/db
    data_connectors:
      default_inferred_data_connector_name:
        class_name: InferredAssetSqlDataConnector
        include_schema_name: true

stores:
  expectations_store:
    class_name: ExpectationsStore
    store_backend:
      class_name: TupleFilesystemStoreBackend
      base_directory: expectations/

  validations_store:
    class_name: ValidationsStore
    store_backend:
      class_name: TupleFilesystemStoreBackend
      base_directory: uncommitted/validations/

data_docs_sites:
  local_site:
    class_name: SiteBuilder
    store_backend:
      class_name: TupleFilesystemStoreBackend
      base_directory: uncommitted/data_docs/local_site/
```

---

## Expectation Suite (JSON snippet)

```json
{
  "expectation_suite_name": "orders_suite",
  "expectations": [
    {
      "expectation_type": "expect_table_row_count_to_be_between",
      "kwargs": { "min_value": 1, "max_value": 10000000 }
    },
    {
      "expectation_type": "expect_column_values_to_not_be_null",
      "kwargs": { "column": "order_id" }
    },
    {
      "expectation_type": "expect_column_values_to_be_between",
      "kwargs": { "column": "amount", "min_value": 0 }
    },
    {
      "expectation_type": "expect_column_values_to_be_in_set",
      "kwargs": { "column": "status", "value_set": ["pending","shipped","delivered","cancelled"] }
    }
  ]
}
```

---

## Common Expectations Reference

| Expectation | Purpose |
|---|---|
| `expect_table_row_count_to_be_between` | Row count within range |
| `expect_column_values_to_not_be_null` | No nulls in column |
| `expect_column_values_to_be_unique` | No duplicates |
| `expect_column_values_to_be_between` | Numeric range check |
| `expect_column_values_to_be_in_set` | Categorical validation |
| `expect_column_values_to_match_regex` | Pattern check |
| `expect_column_mean_to_be_between` | Aggregate stat check |
| `expect_column_pair_values_A_to_be_greater_than_B` | Cross-column comparison |

---

## Integration Pattern: Validate After Extract, Before Load

```
extract_from_source → validate_data → [branch] → load_to_warehouse
                                           ↓ fail
                                       send_alert
```

The `GreatExpectationsOperator` with `fail_task_on_validation_failure=True` handles
the branch automatically: if validation fails, the task fails, downstream load
tasks are skipped, and Airflow's failure callbacks fire.

For explicit branching (e.g., load partial data on soft failure), use
`fail_task_on_validation_failure=False` + `return_json_dict=True` and branch with a
`BranchPythonOperator` on the validation result XCom.

---

## Alternative Tools

| Tool | Approach |
|---|---|
| **dbt tests** | SQL-based assertions; best for warehouse-native testing |
| **Soda** | Python + SodaCL YAML; Airflow provider available |
| **Pandera** | Schema validation for Pandas/Spark DataFrames |
| **Pydantic** | Row-level schema validation in Python |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Spark** | [42_Spark_Integration](../42_Spark_Integration/Theory.md) |
| **Next: KPO Deep Dive** | [44_KubernetesPodOperator_Deep_Dive](../44_KubernetesPodOperator_Deep_Dive/Theory.md) |
