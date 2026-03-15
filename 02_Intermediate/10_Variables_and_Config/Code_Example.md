# 08 — Variables and Config: Code Examples

## Example 1 — Basic Variable.get()

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from datetime import datetime

def process_data():
    # Always call Variable.get() inside the task function, not at module level
    bucket = Variable.get("s3_bucket")
    environment = Variable.get("environment")
    max_rows = int(Variable.get("max_rows"))  # Variables are strings; cast as needed

    print(f"Reading from s3://{bucket}/raw/")
    print(f"Environment: {environment}")
    print(f"Max rows: {max_rows}")

with DAG(
    dag_id="variables_basic",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    task = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )
```

---

## Example 2 — JSON Variable with Default

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from datetime import datetime

# In Airflow UI, set key "pipeline_config" with value:
# {"env": "prod", "retries": 3, "alert_email": "ops@example.com", "batch_size": 500}

def run_pipeline():
    # deserialize_json=True parses the JSON string into a Python dict
    config = Variable.get(
        "pipeline_config",
        default_var='{"env": "dev", "retries": 1, "batch_size": 100}',
        deserialize_json=True,
    )

    env = config.get("env", "dev")
    retries = config.get("retries", 1)
    batch_size = config.get("batch_size", 100)
    alert_email = config.get("alert_email", "dev@example.com")

    print(f"Starting pipeline | env={env} | batch_size={batch_size} | retries={retries}")
    print(f"Alerts will go to: {alert_email}")

with DAG(
    dag_id="variables_json",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    task = PythonOperator(
        task_id="run_pipeline",
        python_callable=run_pipeline,
    )
```

---

## Example 3 — Jinja Template in Operator

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from datetime import datetime

# Set variables in the UI (or CLI):
#   s3_bucket      = my-data-bucket
#   target_schema  = analytics
#   pipeline_config = {"env": "prod", "max_rows": 10000}

with DAG(
    dag_id="variables_jinja",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    # Plain string variable in bash_command
    sync_files = BashOperator(
        task_id="sync_files",
        bash_command=(
            "aws s3 sync /tmp/output/ "
            "s3://{{ var.value.s3_bucket }}/output/{{ ds }}/"
        ),
    )

    # Nested JSON variable access
    log_env = BashOperator(
        task_id="log_env",
        bash_command=(
            "echo 'Running in {{ var.json.pipeline_config.env }} | "
            "max_rows={{ var.json.pipeline_config.max_rows }}'"
        ),
    )

    # Variable in a SQL string
    create_table = PostgresOperator(
        task_id="create_table",
        postgres_conn_id="my_postgres",
        sql=(
            "CREATE TABLE IF NOT EXISTS "
            "{{ var.value.target_schema }}.processed_data "
            "(id SERIAL PRIMARY KEY, loaded_at TIMESTAMPTZ DEFAULT NOW());"
        ),
    )

    sync_files >> log_env >> create_table
```

---

## Example 4 — Setting Variables via Environment Variables

No Python code required — set before starting Airflow (shell, `.env` file, Docker Compose, or Kubernetes Secret).

```bash
# Simple string values
export AIRFLOW_VAR_S3_BUCKET=my-data-bucket
export AIRFLOW_VAR_ENVIRONMENT=production
export AIRFLOW_VAR_MAX_ROWS=5000

# JSON value (single-quoted to prevent shell interpretation of braces)
export AIRFLOW_VAR_PIPELINE_CONFIG='{"env":"prod","retries":3,"alert_email":"ops@example.com"}'
```

Then in your DAG — identical code, no changes needed:

```python
from airflow.models import Variable

def task_fn():
    bucket = Variable.get("s3_bucket")          # reads AIRFLOW_VAR_S3_BUCKET
    config = Variable.get("pipeline_config", deserialize_json=True)  # reads AIRFLOW_VAR_PIPELINE_CONFIG
    print(bucket, config["env"])
```

Verify Airflow sees them:

```bash
airflow variables get s3_bucket
# my-data-bucket

airflow variables list
# s3_bucket
# environment
# max_rows
# pipeline_config
```
