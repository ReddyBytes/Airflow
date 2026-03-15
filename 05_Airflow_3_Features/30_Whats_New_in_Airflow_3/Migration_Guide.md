# Airflow 2 → Airflow 3 Migration Guide

## Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**

---

## Overview

Migrating from Airflow 2 to Airflow 3 requires changes across four areas: dependencies, infrastructure, DAG code, and configuration. This guide walks through each step with exact before/after examples.

Estimated time: 2–8 hours depending on DAG complexity and deployment method.

---

## Step 1: Pre-Migration Checklist

Before touching any code, verify your current state.

```bash
# Check current Airflow version
airflow version

# Check Python version (Airflow 3 requires Python 3.9+)
python --version

# Export current connections (back them up)
airflow connections export connections_backup.json

# Export current variables
airflow variables export variables_backup.json

# List all DAGs to know what you're migrating
airflow dags list

# Check for any SubDAGs (must be migrated)
grep -r "SubDagOperator" dags/
grep -r "subdag" dags/

# Check for Dataset usage (must be renamed to Asset)
grep -r "from airflow.datasets import" dags/
grep -r "Dataset(" dags/

# Check for execution_date usage
grep -r "execution_date" dags/

# Check for provide_context
grep -r "provide_context" dags/
```

Document the output. Every SubDag and Dataset reference needs manual migration.

---

## Step 2: Update Dependencies

### Python Package Update

```bash
# Upgrade Airflow itself
pip install "apache-airflow>=3.0.0"

# If using providers, update them too
pip install "apache-airflow-providers-amazon>=9.0.0"
pip install "apache-airflow-providers-google>=12.0.0"
pip install "apache-airflow-providers-fab>=1.0.0"  # FAB is now a provider

# Freeze updated requirements
pip freeze | grep airflow > requirements.txt
```

### requirements.txt Before/After

```
# Before (Airflow 2)
apache-airflow==2.9.0
apache-airflow-providers-amazon==8.12.0
apache-airflow-providers-google==10.17.0

# After (Airflow 3)
apache-airflow==3.0.0
apache-airflow-providers-amazon==9.0.0
apache-airflow-providers-google==12.0.0
apache-airflow-providers-fab==1.0.0   # FAB moved to provider
```

---

## Step 3: Database Migration

The database schema changed in Airflow 3. The `db init` command no longer exists. Use `db migrate`.

```bash
# Airflow 2 — original setup
airflow db init          # REMOVED in v3
airflow db upgrade       # REMOVED in v3

# Airflow 3 — use migrate for both initial setup and upgrades
airflow db migrate

# Verify migration succeeded
airflow db check
```

If you're running in Docker or Kubernetes, the entrypoint command changes:

```yaml
# Before (Airflow 2)
command: ["bash", "-c", "airflow db init && airflow webserver"]

# After (Airflow 3)
command: ["bash", "-c", "airflow db migrate && airflow api-server"]
```

---

## Step 4: Update DAG Code

This is the most time-intensive step. Work through each pattern systematically.

### 4a: Dataset → Asset (Import Rename)

```python
# Before (Airflow 2)
from airflow.datasets import Dataset

my_dataset = Dataset("s3://my-bucket/data/output.csv")

with DAG(
    dag_id="producer_dag",
    schedule="@daily",
) as dag:
    @task(outlets=[my_dataset])
    def produce():
        # write data
        pass
```

```python
# After (Airflow 3)
from airflow.sdk import Asset

my_asset = Asset("s3://my-bucket/data/output.csv")

with DAG(
    dag_id="producer_dag",
    schedule="@daily",
) as dag:
    @task(outlets=[my_asset])
    def produce():
        # write data
        pass
```

For consumer DAGs:

```python
# Before (Airflow 2)
from airflow.datasets import Dataset

with DAG(
    dag_id="consumer_dag",
    schedule=[Dataset("s3://my-bucket/data/output.csv")],
) as dag:
    ...
```

```python
# After (Airflow 3)
from airflow.sdk import Asset

with DAG(
    dag_id="consumer_dag",
    schedule=[Asset("s3://my-bucket/data/output.csv")],
) as dag:
    ...
```

### 4b: SubDAG → TaskGroup

Every `SubDagOperator` must be converted. This is not optional — the operator does not exist in v3.

```python
# Before (Airflow 2) — SubDAG pattern
from airflow.operators.subdag import SubDagOperator
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

def etl_subdag(parent_dag_id, child_dag_id, default_args):
    with DAG(
        dag_id=f"{parent_dag_id}.{child_dag_id}",
        default_args=default_args,
    ) as dag:
        extract = BashOperator(task_id="extract", bash_command="extract.sh")
        transform = BashOperator(task_id="transform", bash_command="transform.sh")
        load = BashOperator(task_id="load", bash_command="load.sh")
        extract >> transform >> load
    return dag

with DAG(
    dag_id="main_pipeline",
    default_args={"start_date": datetime(2024, 1, 1)},
    schedule="@daily",
) as dag:
    start = BashOperator(task_id="start", bash_command="echo start")

    etl = SubDagOperator(
        task_id="etl",
        subdag=etl_subdag("main_pipeline", "etl", {"start_date": datetime(2024, 1, 1)}),
    )

    end = BashOperator(task_id="end", bash_command="echo end")
    start >> etl >> end
```

```python
# After (Airflow 3) — TaskGroup pattern
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from datetime import datetime

with DAG(
    dag_id="main_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
) as dag:
    start = BashOperator(task_id="start", bash_command="echo start")

    with TaskGroup("etl") as etl:
        extract = BashOperator(task_id="extract", bash_command="extract.sh")
        transform = BashOperator(task_id="transform", bash_command="transform.sh")
        load = BashOperator(task_id="load", bash_command="load.sh")
        extract >> transform >> load

    end = BashOperator(task_id="end", bash_command="echo end")
    start >> etl >> end
```

### 4c: Remove provide_context

```python
# Before (Airflow 2)
from airflow.operators.python import PythonOperator

def my_function(**context):
    print(context["execution_date"])

task = PythonOperator(
    task_id="my_task",
    python_callable=my_function,
    provide_context=True,   # REMOVE THIS
)
```

```python
# After (Airflow 3)
from airflow.operators.python import PythonOperator

def my_function(**context):
    print(context["logical_date"])   # Also rename execution_date here

task = PythonOperator(
    task_id="my_task",
    python_callable=my_function,
    # provide_context is gone — context is always provided
)
```

### 4d: execution_date → logical_date

`execution_date` is removed from the context and from template variables.

```python
# Before (Airflow 2)
# In Python callables:
def process(**context):
    exec_date = context["execution_date"]
    ds = context["ds"]  # string form of execution_date — still valid in v3

# In Jinja templates:
bash_command = "echo {{ execution_date }}"

# In macros:
bash_command = "echo {{ execution_date.strftime('%Y-%m-%d') }}"
```

```python
# After (Airflow 3)
def process(**context):
    logical_date = context["logical_date"]    # renamed
    ds = context["ds"]                         # still works

# In Jinja templates:
bash_command = "echo {{ logical_date }}"

# In macros:
bash_command = "echo {{ logical_date.strftime('%Y-%m-%d') }}"
```

Template variables that changed:

| Airflow 2 | Airflow 3 |
|-----------|-----------|
| `{{ execution_date }}` | `{{ logical_date }}` |
| `{{ execution_date_nodash }}` | `{{ logical_date_nodash }}` |
| `context["execution_date"]` | `context["logical_date"]` |
| `context["prev_execution_date"]` | `context["prev_logical_date"]` |
| `context["next_execution_date"]` | `context["next_logical_date"]` |

---

## Step 5: Update Docker Compose

This is the infrastructure change. You need to add `dag-processor` and rename `webserver` to `api-server`.

```yaml
# Before (Airflow 2 docker-compose.yml) — simplified
version: "3.8"
services:
  postgres:
    image: postgres:15

  webserver:
    image: apache/airflow:2.9.0
    command: webserver
    ports:
      - "8080:8080"
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0

  scheduler:
    image: apache/airflow:2.9.0
    command: scheduler
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow

  worker:
    image: apache/airflow:2.9.0
    command: celery worker
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow

  redis:
    image: redis:7
```

```yaml
# After (Airflow 3 docker-compose.yml) — simplified
version: "3.8"
services:
  postgres:
    image: postgres:15

  api-server:               # renamed from webserver
    image: apache/airflow:3.0.0
    command: api-server     # renamed from webserver
    ports:
      - "8080:8080"
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0

  dag-processor:            # NEW: required component
    image: apache/airflow:3.0.0
    command: dag-processor  # NEW command
    volumes:
      - ./dags:/opt/airflow/dags
    environment:
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow

  scheduler:
    image: apache/airflow:3.0.0
    command: scheduler
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow

  worker:
    image: apache/airflow:3.0.0
    command: celery worker
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow

  redis:
    image: redis:7
```

---

## Step 6: Update Configuration (airflow.cfg)

```ini
# Before (Airflow 2 airflow.cfg)
[webserver]
base_url = http://localhost:8080
web_server_port = 8080
rbac = True
authenticate = True
auth_backend = airflow.contrib.auth.backends.password_auth

[scheduler]
dag_dir_list_interval = 300

# After (Airflow 3 airflow.cfg)
[api_server]
base_url = http://localhost:8080
port = 8080

[core]
# Set auth manager explicitly (FAB is no longer default)
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
# For development only:
# auth_manager = airflow.auth.managers.simple.SimpleAuthManager

[dag_processor]
# DAG parsing config moved here from [scheduler]
dag_dir_list_interval = 300
```

---

## Step 7: Update Connections and Variables

Connections and variables are backward-compatible — you don't need to recreate them. However, if you exported them in Step 1, you can import them fresh:

```bash
# Import connections
airflow connections import connections_backup.json

# Import variables
airflow variables import variables_backup.json
```

If you have connections using deprecated connection types, check the provider changelog.

---

## Step 8: Update REST API Clients

If you have any external systems calling the Airflow REST API, update the base path:

```python
# Before (Airflow 2)
AIRFLOW_API_BASE = "http://airflow:8080/api/v1"

response = requests.post(
    f"{AIRFLOW_API_BASE}/dags/my_dag/dagRuns",
    json={"conf": {"key": "value"}},
    auth=("admin", "admin"),
)

# After (Airflow 3)
AIRFLOW_API_BASE = "http://airflow:8080/api/v2"  # version bump

response = requests.post(
    f"{AIRFLOW_API_BASE}/dags/my_dag/dagRuns",
    json={"conf": {"key": "value"}},
    auth=("admin", "admin"),
    # OR use JWT token:
    headers={"Authorization": f"Bearer {jwt_token}"},
)
```

---

## Step 9: Test and Validate

```bash
# 1. Run the database migration
airflow db migrate

# 2. Start services
docker-compose up -d

# 3. Check all services are healthy
docker-compose ps

# 4. Verify DAGs are parsing (check dag-processor logs)
docker-compose logs dag-processor

# 5. List parsed DAGs
airflow dags list

# 6. Trigger a test DAG run
airflow dags trigger my_dag

# 7. Check the run completed
airflow dags list-runs --dag-id my_dag

# 8. Verify assets work (if applicable)
airflow assets list

# 9. Test the UI — open http://localhost:8080
# Verify:
# - All DAGs appear
# - Graph view renders
# - Task logs are accessible
# - Assets/lineage view works
```

---

## Common Migration Errors and Fixes

### Error: `No module named 'airflow.datasets'`

```
ImportError: cannot import name 'Dataset' from 'airflow.datasets'
```

Fix: Change `from airflow.datasets import Dataset` to `from airflow.sdk import Asset` and rename all `Dataset(...)` to `Asset(...)`.

### Error: `SubDagOperator not found`

```
ImportError: cannot import name 'SubDagOperator' from 'airflow.operators.subdag'
```

Fix: Migrate all SubDAGs to TaskGroups (see Step 4b above).

### Error: `provide_context is not a valid parameter`

```
TypeError: __init__() got an unexpected keyword argument 'provide_context'
```

Fix: Remove `provide_context=True` from all `PythonOperator` instantiations.

### Error: `DAGs not appearing in UI`

If the DAG Processor is not running, DAGs will never be parsed and will not appear.

Fix: Ensure `airflow dag-processor` is running as a service.

### Error: `execution_date` KeyError in context

```
KeyError: 'execution_date'
```

Fix: Replace all `context["execution_date"]` with `context["logical_date"]` and all `{{ execution_date }}` template vars with `{{ logical_date }}`.

---

## Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**
