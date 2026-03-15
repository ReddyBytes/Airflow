# 🔗 dbt Integration — Code Examples

Two patterns for running dbt from Airflow: the simple BashOperator approach, and the production-grade astronomer-cosmos DbtDag factory.

---

## Example 1 — dbt Core via BashOperator

The simple approach. Works for small projects or teams just getting started.

```python
"""
dbt_bash_pipeline.py
--------------------
Runs a dbt project using BashOperator.

Requirements:
  - dbt installed in the Airflow environment (pip install dbt-core dbt-postgres)
  - dbt project at /opt/airflow/dbt/my_project
  - profiles.yml at /opt/airflow/dbt/profiles/profiles.yml
  - A Postgres connection named "postgres_warehouse" in Airflow
"""

from airflow.sdk import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator
import os
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────
DBT_PROJECT_DIR = "/opt/airflow/dbt/my_project"
DBT_PROFILES_DIR = "/opt/airflow/dbt/profiles"
DBT_TARGET = "prod"

# ── DAG definition ───────────────────────────────────────────────
with DAG(
    dag_id="dbt_bash_pipeline",
    description="Run dbt project using BashOperator",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["dbt", "transform", "example"],
) as dag:

    # ── Step 1: Install dbt package dependencies ─────────────────
    # Runs `dbt deps` to pull packages from packages.yml
    # This is idempotent — safe to run every time
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"""
            cd {DBT_PROJECT_DIR} && \
            dbt deps \
              --profiles-dir {DBT_PROFILES_DIR} \
              --target {DBT_TARGET}
        """,
    )

    # ── Step 2: Run all dbt models ───────────────────────────────
    # {{ ds }} is Airflow's execution date (YYYY-MM-DD)
    # passed to dbt as a variable named "execution_date"
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"""
            cd {DBT_PROJECT_DIR} && \
            dbt run \
              --profiles-dir {DBT_PROFILES_DIR} \
              --target {DBT_TARGET} \
              --vars '{{"execution_date": "{{{{ ds }}}}", "env": "{DBT_TARGET}"}}' \
              --select +mart_orders+    \
              --full-refresh false
        """,
    )

    # ── Step 3: Run dbt tests ────────────────────────────────────
    # Fails the task if any test fails
    # --store-failures saves failing rows to the database for debugging
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"""
            cd {DBT_PROJECT_DIR} && \
            dbt test \
              --profiles-dir {DBT_PROFILES_DIR} \
              --target {DBT_TARGET} \
              --store-failures \
              --select +mart_orders+
        """,
    )

    # ── Step 4: Generate docs (optional) ─────────────────────────
    dbt_docs = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"""
            cd {DBT_PROJECT_DIR} && \
            dbt docs generate \
              --profiles-dir {DBT_PROFILES_DIR} \
              --target {DBT_TARGET}
        """,
        # Don't fail the whole pipeline if docs generation fails
        trigger_rule="all_done",
    )

    # ── Task dependencies ────────────────────────────────────────
    dbt_deps >> dbt_run >> dbt_test >> dbt_docs
```

---

## Example 2 — astronomer-cosmos DbtDag Factory

The production approach. Cosmos parses your dbt project and generates one Airflow task per dbt model.

**Install:**
```bash
pip install "astronomer-cosmos[dbt-postgres]"
# For Snowflake: pip install "astronomer-cosmos[dbt-snowflake]"
# For BigQuery: pip install "astronomer-cosmos[dbt-bigquery]"
```

```python
"""
dbt_cosmos_pipeline.py
-----------------------
Uses astronomer-cosmos to auto-generate Airflow tasks from a dbt project.

Each dbt model becomes an Airflow task.
Dependencies between tasks mirror the dbt ref() relationships.
Full DAG lineage visible in Airflow UI.

Requirements:
  pip install "astronomer-cosmos[dbt-postgres]"
"""

from cosmos import (
    DbtDag,
    DbtTaskGroup,
    ProjectConfig,
    ProfileConfig,
    ExecutionConfig,
    RenderConfig,
)
from cosmos.profiles import PostgresUserPasswordProfileMapping
from airflow.sdk import DAG, task
from datetime import datetime
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────
DBT_PROJECT_PATH = Path("/opt/airflow/dbt/my_project")
DBT_EXECUTABLE = "/usr/local/bin/dbt"

# ── Profile config: how Airflow connects to your warehouse ───────
# Uses the "postgres_warehouse" Airflow connection
profile_config = ProfileConfig(
    profile_name="my_project",
    target_name="prod",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id="postgres_warehouse",
        profile_args={
            "schema": "analytics",
            "threads": 4,
        },
    ),
)

# ── Pattern A: DbtDag — Cosmos owns the entire DAG ───────────────
# Use this when dbt is the whole pipeline
dbt_full_dag = DbtDag(
    dag_id="dbt_cosmos_full",
    description="Full dbt project run via cosmos",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["dbt", "cosmos", "transform"],

    # dbt project location
    project_config=ProjectConfig(
        dbt_project_path=DBT_PROJECT_PATH,
    ),

    # How to connect to the warehouse
    profile_config=profile_config,

    # How to execute dbt commands
    execution_config=ExecutionConfig(
        dbt_executable_path=DBT_EXECUTABLE,
    ),

    # Optional: filter which models to include
    render_config=RenderConfig(
        # Run only models in the marts/ folder and their upstream deps
        select=["path:models/marts"],
        # Exclude specific models
        # exclude=["my_slow_model"],
    ),

    # Extra args passed to every generated operator
    operator_args={
        "install_deps": True,           # run dbt deps before each task
        "full_refresh": False,
        "vars": {"execution_date": "{{ ds }}"},
    },
)


# ── Pattern B: DbtTaskGroup — dbt is part of a larger DAG ────────
# Use this when dbt transforms sit between extract and load tasks
with DAG(
    dag_id="dbt_cosmos_taskgroup",
    description="dbt as part of a larger ETL pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["dbt", "cosmos", "etl"],
) as dag:

    @task
    def extract_raw_data():
        """Simulate extracting data from a source system."""
        print("Extracting data from API...")
        # In real life: call an API, load to raw schema
        return {"rows_loaded": 1500}

    # ── dbt TaskGroup: generates tasks for all dbt models ────────
    # Dependencies between models derived from ref() automatically
    transform_with_dbt = DbtTaskGroup(
        group_id="dbt_transform",

        project_config=ProjectConfig(
            dbt_project_path=DBT_PROJECT_PATH,
        ),
        profile_config=profile_config,
        execution_config=ExecutionConfig(
            dbt_executable_path=DBT_EXECUTABLE,
        ),
        render_config=RenderConfig(
            # Only run staging and mart models (skip seeds, snapshots)
            select=["path:models/staging", "path:models/marts"],
        ),
        operator_args={
            "install_deps": True,
            "vars": {"execution_date": "{{ ds }}"},
        },
    )

    @task
    def publish_results():
        """After dbt succeeds, publish results to BI tool."""
        print("Refreshing dashboard cache...")
        return "done"

    # ── Task dependencies ────────────────────────────────────────
    extract_raw_data() >> transform_with_dbt >> publish_results()
```

---

## Example 3 — dbt Cloud via API

If you use dbt Cloud (the hosted version), trigger jobs via the dbt Cloud API:

```python
"""
dbt_cloud_trigger.py
---------------------
Triggers a dbt Cloud job and waits for it to complete.

Requirements:
  pip install apache-airflow-providers-dbt-cloud
  Airflow connection: dbt_cloud_default
    - Connection type: dbt Cloud
    - API token: your dbt Cloud API token
    - Account ID: your dbt Cloud account ID
"""

from airflow.sdk import DAG
from airflow.providers.dbt.cloud.operators.dbt import DbtCloudRunJobOperator
from airflow.providers.dbt.cloud.sensors.dbt import DbtCloudJobRunSensor
from datetime import datetime

with DAG(
    dag_id="dbt_cloud_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    # Trigger a dbt Cloud job and wait for it to complete
    run_dbt_job = DbtCloudRunJobOperator(
        task_id="run_dbt_cloud_job",
        dbt_cloud_conn_id="dbt_cloud_default",
        job_id=12345,               # Your dbt Cloud job ID
        check_interval=30,          # Poll every 30 seconds
        timeout=3600,               # Fail if still running after 1 hour
        # Optional: pass additional config overrides
        additional_run_config={
            "steps_override": ["dbt run", "dbt test"],
        },
    )
```

---

## dbt profiles.yml — Connecting to Your Warehouse

If using the BashOperator approach, you need a `profiles.yml`:

```yaml
# /opt/airflow/dbt/profiles/profiles.yml
my_project:
  target: prod
  outputs:
    prod:
      type: postgres
      host: "{{ env_var('DBT_HOST') }}"
      port: 5432
      user: "{{ env_var('DBT_USER') }}"
      password: "{{ env_var('DBT_PASSWORD') }}"
      dbname: analytics
      schema: marts
      threads: 4
```

Set the environment variables in Airflow:
```bash
# In airflow.cfg or via environment variables
AIRFLOW__CORE__FERNET_KEY=...
DBT_HOST=your-db-host.us-east-1.rds.amazonaws.com
DBT_USER=dbt_user
DBT_PASSWORD=your-password
```

Or use Airflow's Secrets Backend to populate them at runtime.
