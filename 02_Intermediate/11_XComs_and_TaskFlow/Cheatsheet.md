# 09 — XComs: Cheatsheet

## Push and Pull Syntax

```python
# --- Classic style (PythonOperator with provide_context or **context) ---

# Push with explicit key
def push_task(ti, **context):
    ti.xcom_push(key="my_key", value="my_value")

# Push via return value (key = "return_value" automatically)
def push_task():
    return "my_value"

# Pull by task_id and key
def pull_task(ti, **context):
    val = ti.xcom_pull(task_ids="push_task", key="my_key")

# Pull return_value (key defaults to "return_value")
def pull_task(ti, **context):
    val = ti.xcom_pull(task_ids="push_task")

# Pull from multiple tasks (returns a list)
def pull_multi(ti, **context):
    vals = ti.xcom_pull(task_ids=["task_a", "task_b"], key="status")
```

---

## TaskFlow API (@task Decorator)

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(schedule=None, start_date=datetime(2024, 1, 1), catchup=False)
def my_dag():

    @task
    def extract() -> str:
        return "s3://bucket/file.csv"   # auto-pushed as XCom

    @task
    def transform(path: str) -> dict:
        return {"rows": 1000, "path": path}  # returned dict is auto-pushed

    @task
    def load(summary: dict):
        print(summary["rows"])

    # Airflow infers the XCom dependency from the function call
    load(transform(extract()))

my_dag()
```

---

## XCom Size Guidelines

| Size | OK to XCom? | Recommendation |
|---|---|---|
| A string (filename, ID, status) | Yes | Push directly |
| A small dict or list (<1 KB) | Yes | Push directly |
| A list of IDs (hundreds of rows) | Caution | Test metadata DB impact |
| A Pandas DataFrame | No | Write to S3/GCS, push the path |
| A file > 1 MB | No | Write to external storage |

---

## When to Use XCom vs External Storage

| Use XCom | Use External Storage (S3/GCS/DB) |
|---|---|
| Passing a filename or key | Passing actual file contents |
| Sharing a job ID or status code | Sharing a DataFrame or large result set |
| Coordinating task parameters | Any data you'd query or join later |

---

## Key Identifiers

| Field | Default | Notes |
|---|---|---|
| `key` | `"return_value"` | When using return values or `@task` |
| `task_ids` | Required for pull | Pass a string or list of strings |
| `dag_id` | Current DAG | Override to pull from a different DAG |
| `run_id` | Current run | Override to pull from a specific run |

---

## XCom Cleanup

- XComs are cleared when you **clear a task instance** from the UI.
- They are deleted when the **DAG run** is deleted.
- To clear all XComs for a run manually:
  ```python
  # Inside a task
  session.query(XCom).filter(XCom.run_id == context["run_id"]).delete()
  ```
- For high-frequency DAGs, set a short **DAG run retention** policy to prevent metadata DB bloat.
