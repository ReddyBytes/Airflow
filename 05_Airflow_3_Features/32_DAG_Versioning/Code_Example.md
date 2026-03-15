# DAG Versioning — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**

---

## Example 1: Observing Versioning in Action

The most educational way to understand DAG versioning is to trigger it deliberately and watch the version counter increment.

Start with a simple DAG:

```python
# dags/versioned_pipeline.py  — VERSION 1
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id="versioned_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["versioning-demo"],
) as dag:

    def extract():
        print("Extracting data...")

    def load():
        print("Loading data...")

    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    load_task    = PythonOperator(task_id="load",    python_callable=load)

    extract_task >> load_task
```

After deploying, check the version:

```bash
# List versions for this DAG
airflow dags versions list --dag-id versioned_pipeline

# Output:
# dag_id              version  created_at
# versioned_pipeline  1        2026-01-10 09:00:00
```

Now add a transform task between extract and load (this is a structural change):

```python
# dags/versioned_pipeline.py  — VERSION 2
# Added: transform task between extract and load

    def transform():
        print("Transforming data...")

    extract_task   = PythonOperator(task_id="extract",   python_callable=extract)
    transform_task = PythonOperator(task_id="transform", python_callable=transform)
    load_task      = PythonOperator(task_id="load",      python_callable=load)

    extract_task >> transform_task >> load_task
```

After saving the file, the DAG Processor detects the structural change:

```bash
airflow dags versions list --dag-id versioned_pipeline

# Output:
# dag_id              version  created_at
# versioned_pipeline  1        2026-01-10 09:00:00
# versioned_pipeline  2        2026-03-15 11:05:00
```

Any DAG runs scheduled before the change are still linked to version 1. New runs use version 2.

---

## Example 2: Checking Version History via CLI

```bash
# List all versions of a DAG
airflow dags versions list --dag-id versioned_pipeline

# Show details for a specific version
airflow dags versions get --dag-id versioned_pipeline --version-number 1

# Show which version is currently active (latest)
airflow dags versions list --dag-id versioned_pipeline --limit 1

# List versions across ALL DAGs (useful for auditing)
airflow dags versions list

# Show which version a specific run used
airflow dags list-runs --dag-id versioned_pipeline --output table
# The output includes a version_number column

# Prune old versions, keep only last 10
airflow dags versions prune --dag-id versioned_pipeline --keep-last 10
```

---

## Example 3: Triggering a Run Against a Specific Version

Scenario: version 3 introduced a bug. You want to re-run yesterday's data using version 2 while you fix version 3.

```bash
# See available versions
airflow dags versions list --dag-id versioned_pipeline
# dag_id              version  created_at
# versioned_pipeline  1        2026-01-10 09:00:00
# versioned_pipeline  2        2026-02-01 14:32:00
# versioned_pipeline  3        2026-03-15 11:05:00  <-- has a bug

# Trigger a run using version 2
airflow dags trigger versioned_pipeline \
  --dag-version 2 \
  --logical-date 2026-03-14T00:00:00+00:00 \
  --note "Emergency re-run using v2 while v3 is fixed"

# Verify the run was created with version 2
airflow dags list-runs --dag-id versioned_pipeline --limit 5
```

The triggered run will execute the version 2 task graph (without the buggy task from version 3), while future scheduled runs continue to use version 3 until you fix and redeploy.

---

## Example 4: DAG Bundle Configuration

DAG Bundles are how you tell Airflow 3 where to find DAG files. Each bundle is a named source. Versioning records which bundle and which bundle revision produced each DAG version.

### Local directory bundle (default, simplest)

```python
# airflow_settings.py or environment variable approach
# Set via environment variables:

AIRFLOW__DAG_BUNDLES__BACKENDS = """
[
  {
    "name": "local_dags",
    "classpath": "airflow.dag_processing.bundles.local.LocalDagBundle",
    "kwargs": {
      "path": "/opt/airflow/dags",
      "refresh_interval": 30
    }
  }
]
"""
```

### Git-based bundle (tracks commits)

```python
# When using the Git bundle, each DAG version record includes the commit SHA
# This creates a complete audit trail: run → DAG version → git commit

AIRFLOW__DAG_BUNDLES__BACKENDS = """
[
  {
    "name": "production_dags",
    "classpath": "airflow.dag_processing.bundles.git.GitDagBundle",
    "kwargs": {
      "repo_url": "https://github.com/myorg/airflow-dags.git",
      "branch": "main",
      "refresh_interval": 60,
      "subdir": "dags/"
    }
  }
]
"""
```

With a Git bundle, `airflow dags versions list` shows the commit SHA:

```bash
airflow dags versions list --dag-id versioned_pipeline

# dag_id              version  bundle            commit_sha  created_at
# versioned_pipeline  1        production_dags   abc123f     2026-01-10 09:00:00
# versioned_pipeline  2        production_dags   def456a     2026-02-01 14:32:00
# versioned_pipeline  3        production_dags   ghi789b     2026-03-15 11:05:00
```

### Docker Compose with DAG bundle config

```yaml
# docker-compose.yml
x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    AIRFLOW__DAG_BUNDLES__BACKENDS: >-
      [{"name": "local", "classpath": "airflow.dag_processing.bundles.local.LocalDagBundle",
        "kwargs": {"path": "/opt/airflow/dags", "refresh_interval": 30}}]
    AIRFLOW__CORE__MAX_DAG_VERSIONS: "25"
  volumes:
    - ./dags:/opt/airflow/dags

services:
  dag-processor:
    <<: *airflow-common
    command: dag-processor
    # The dag-processor is the ONLY component that reads DAG files from disk
    # All other components read serialized versions from the DB via the API

  scheduler:
    <<: *airflow-common
    command: scheduler
    # Scheduler reads serialized DAG versions from DB, never from disk

  api-server:
    <<: *airflow-common
    command: api-server
    ports:
      - "8080:8080"
```

---

## Example 5: Viewing Version Differences Programmatically

If you need to compare DAG versions in code (e.g., in a deployment script or test):

```python
# scripts/check_dag_version.py
"""
Utility to compare two DAG versions and report structural differences.
Run after deploying to verify what changed.
"""
import json
import subprocess
import sys


def get_version_tasks(dag_id: str, version: int) -> set[str]:
    """Return the set of task_ids in a given DAG version."""
    result = subprocess.run(
        ["airflow", "dags", "versions", "get",
         "--dag-id", dag_id, "--version-number", str(version),
         "--output", "json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not fetch version {version}: {result.stderr}")

    data = json.loads(result.stdout)
    # The serialized_dag contains task definitions
    serialized = json.loads(data["serialized_dag"])
    return {task["task_id"] for task in serialized.get("tasks", [])}


def compare_versions(dag_id: str, old_version: int, new_version: int) -> None:
    old_tasks = get_version_tasks(dag_id, old_version)
    new_tasks = get_version_tasks(dag_id, new_version)

    added   = new_tasks - old_tasks
    removed = old_tasks - new_tasks
    kept    = old_tasks & new_tasks

    print(f"\nDAG: {dag_id}  v{old_version} → v{new_version}")
    print(f"  Tasks kept:    {sorted(kept)}")
    print(f"  Tasks added:   {sorted(added)}")
    print(f"  Tasks removed: {sorted(removed)}")

    if not added and not removed:
        print("  No structural change detected.")
    else:
        print(f"\n  CHANGE SUMMARY: +{len(added)} added, -{len(removed)} removed")


if __name__ == "__main__":
    compare_versions("versioned_pipeline", old_version=1, new_version=2)
```

Running this after a deployment gives you a quick sanity check:

```
DAG: versioned_pipeline  v1 → v2
  Tasks kept:    ['extract', 'load']
  Tasks added:   ['transform']
  Tasks removed: []

  CHANGE SUMMARY: +1 added, -0 removed
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**
