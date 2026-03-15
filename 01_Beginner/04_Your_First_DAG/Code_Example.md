# 03 · DAGs Deep Dive — Code Example

Two complete, runnable DAG examples with explanatory comments throughout.

Copy these files into your `./dags/` folder and they will appear in the Airflow UI within 30 seconds.

---

## Example 1: Complete ETL DAG with Four Task Types

This DAG demonstrates:
- Proper imports and project structure
- `default_args` with retry config
- All four commonly used operators: `EmptyOperator`, `BashOperator`, `PythonOperator`
- Linear and fan-out dependency patterns
- Jinja templating in bash commands

```python
# dags/example_etl_dag.py
#
# PURPOSE: Demonstrates a complete ETL pipeline using four different operators.
#          Extracts data, runs parallel transforms, loads results, then notifies.
#
# SCHEDULE: Daily at 6am UTC
# OWNER:    data-team

# ─── Imports ─────────────────────────────────────────────────────────────────
# Standard library
from datetime import datetime, timedelta

# Airflow core
from airflow import DAG

# Operators — each one is a different "type" of task
from airflow.operators.empty import EmptyOperator       # Placeholder / sentinel task
from airflow.operators.bash import BashOperator          # Runs a shell command
from airflow.operators.python import PythonOperator      # Runs a Python function

# ─── Default Arguments ────────────────────────────────────────────────────────
# These settings apply to EVERY task in the DAG unless overridden on the task.
# Think of this as the "house rules" for the kitchen.
default_args = {
    # Who owns this DAG? Shown in the UI and in alert emails.
    "owner": "data-team",

    # If a task fails, wait 5 minutes and try again. Do this up to 2 times.
    "retries": 2,
    "retry_delay": timedelta(minutes=5),

    # Send an email alert when a task fails (after all retries are exhausted).
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["data-alerts@company.com"],

    # Kill the task if it has been running for more than 1 hour.
    # Prevents silent hangs from blocking the queue.
    "execution_timeout": timedelta(hours=1),
}


# ─── Python Task Functions ────────────────────────────────────────────────────
# Define the Python logic for PythonOperator tasks BEFORE the DAG context.
# These are plain Python functions — no Airflow-specific code inside them.
# The **context argument receives Airflow template variables (ds, run_id, etc.)

def extract_from_api(**context):
    """
    Simulates pulling data from an external REST API.
    In production, you would use requests or httpx here.
    The 'ds' context variable is the logical date (YYYY-MM-DD string).
    """
    logical_date = context["ds"]  # e.g., "2024-01-15"
    print(f"[extract] Pulling data for date: {logical_date}")
    # In real code: response = requests.get(f"https://api.example.com/data?date={logical_date}")
    print("[extract] Successfully pulled 1,234 records from API")


def transform_for_region(region: str, **context):
    """
    Simulates a transformation for a specific sales region.
    Using a closure-style approach — we will use partial() to pass the region.
    In production, this would reshape/clean/validate the data.
    """
    logical_date = context["ds"]
    print(f"[transform] Processing region={region} for date={logical_date}")
    # In real code: apply pandas transformations, filter, aggregate, etc.
    print(f"[transform] Region {region}: 300 clean records produced")


def load_to_warehouse(**context):
    """
    Simulates loading the transformed data into a data warehouse.
    Uses DELETE + INSERT pattern for idempotency:
    re-running this task for the same date is safe.
    """
    logical_date = context["ds"]
    print(f"[load] Writing to warehouse for date: {logical_date}")
    # In real code:
    #   hook = PostgresHook(postgres_conn_id="my_warehouse")
    #   hook.run(f"DELETE FROM sales WHERE date = '{logical_date}'")
    #   hook.run("INSERT INTO sales SELECT * FROM staging")
    print("[load] Successfully loaded 900 records")


# ─── DAG Definition ───────────────────────────────────────────────────────────
# The `with DAG(...) as dag:` context manager is the modern way to define DAGs.
# All tasks created inside this block are automatically associated with this DAG.

with DAG(
    # dag_id MUST be unique across all DAGs in your Airflow environment.
    dag_id="example_etl_dag",

    # A human-readable description shown in the UI.
    description="Daily ETL: API → Transform (3 regions) → Warehouse → Notify",

    # Inherit the default_args we defined above.
    default_args=default_args,

    # The date from which Airflow begins calculating schedule intervals.
    # ALWAYS use a fixed date — never datetime.now().
    start_date=datetime(2024, 1, 1),

    # Cron expression: run at 6:00am UTC every day.
    # "0 6 * * *" = minute=0, hour=6, any day, any month, any weekday
    schedule_interval="0 6 * * *",

    # catchup=False means: do NOT create runs for all the daily intervals
    # between start_date (Jan 1) and today. Only run going forward.
    catchup=False,

    # Tags help you filter DAGs in the UI when you have many.
    tags=["etl", "sales", "daily"],

    # Prevent two runs of this DAG from overlapping.
    # If the 6am run is still going at 7am, do not start the 7am run.
    max_active_runs=1,

) as dag:

    # ── Task 1: Start sentinel ────────────────────────────────────────────────
    # EmptyOperator (previously called DummyOperator) does nothing by itself.
    # It is used as a visual "start" marker in the DAG graph.
    # Useful when multiple tasks fan out from a single entry point.
    start = EmptyOperator(
        task_id="start",
    )

    # ── Task 2: Extract ───────────────────────────────────────────────────────
    # PythonOperator runs a Python function. Pass the function with python_callable.
    # The function receives Airflow context via **kwargs if you set provide_context=True
    # (in older Airflow) or if your function accepts **context or **kwargs (Airflow 2.x).
    extract = PythonOperator(
        task_id="extract_from_api",
        python_callable=extract_from_api,
        # In Airflow 2.x, context is passed automatically if the function accepts **kwargs
    )

    # ── Tasks 3a, 3b, 3c: Parallel regional transforms ───────────────────────
    # These three tasks run in PARALLEL after extract.
    # We use functools.partial to pass different arguments to the same function.
    from functools import partial

    transform_north = PythonOperator(
        task_id="transform_north",
        python_callable=partial(transform_for_region, "north"),
    )

    transform_south = PythonOperator(
        task_id="transform_south",
        python_callable=partial(transform_for_region, "south"),
    )

    transform_east = PythonOperator(
        task_id="transform_east",
        python_callable=partial(transform_for_region, "east"),
    )

    # ── Task 4: Load ──────────────────────────────────────────────────────────
    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_to_warehouse,
        # This task overrides the global retry setting — 3 retries instead of 2.
        retries=3,
        retry_delay=timedelta(minutes=10),
    )

    # ── Task 5: BashOperator example ─────────────────────────────────────────
    # BashOperator runs a shell command. Useful for invoking CLI tools,
    # running scripts, or executing dbt commands.
    # Note: {{ ds }} is a Jinja template that renders to the logical date string.
    notify = BashOperator(
        task_id="send_notification",
        bash_command=(
            "echo 'ETL complete for {{ ds }}. "
            "Run ID: {{ run_id }}. "
            "DAG: {{ dag.dag_id }}'"
        ),
        # In real life, you would call a Slack webhook or send an email via curl:
        # bash_command="curl -X POST $SLACK_WEBHOOK -d '{\"text\": \"ETL done: {{ ds }}\"}'",
    )

    # ── Task 6: End sentinel ──────────────────────────────────────────────────
    end = EmptyOperator(
        task_id="end",
    )

    # ─── Task Dependencies ────────────────────────────────────────────────────
    # This is where we wire the tasks together into a graph.
    #
    # Pattern here:
    #   start
    #     └── extract
    #           ├── transform_north ──┐
    #           ├── transform_south ──┼── load ── notify ── end
    #           └── transform_east ───┘
    #
    # Read >> as "must come before"

    # start must complete before extract begins
    start >> extract

    # extract triggers all three transforms in parallel (fan-out)
    extract >> [transform_north, transform_south, transform_east]

    # ALL three transforms must succeed before load begins (fan-in)
    [transform_north, transform_south, transform_east] >> load

    # load → notify → end (linear chain)
    load >> notify >> end
```

---

## Example 2: Parametrized DAG Using Airflow Variables

This DAG demonstrates:
- Reading configuration from Airflow Variables
- Dynamic behavior based on environment (dev vs prod)
- Safe default values when variables are not set
- Using `dag_run.conf` for per-run overrides

```python
# dags/example_parametrized_dag.py
#
# PURPOSE: Shows how to make a DAG configurable without editing code.
#          Reads target environment and table names from Airflow Variables.
#          Can also accept per-run configuration via the trigger UI.
#
# SETUP:   Before running this DAG, set these Variables in the Airflow UI
#          (Admin → Variables) or via CLI:
#
#          airflow variables set environment "production"
#          airflow variables set target_schema "analytics"
#          airflow variables set max_records "50000"
#
# SCHEDULE: Manual only (schedule_interval=None)

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable  # Import to read Airflow Variables


# ─── Read Variables at Parse Time ────────────────────────────────────────────
# Variables.get() can be called at the module level (parse time) but be careful:
# - The Scheduler parses this file every 30 seconds
# - Each Variable.get() hits the Metadata Database
# - For many variables or many DAGs, this adds DB load
#
# Alternative: read inside task functions (at runtime, not parse time).
# Here we show both patterns.

# Read a variable with a safe default value.
# If "environment" variable does not exist in Airflow, defaults to "dev".
ENVIRONMENT = Variable.get("environment", default_var="dev")

# Read a JSON variable (deserialize=True parses the value as JSON)
# Example: airflow variables set pipeline_config '{"batch_size": 1000}'
# PIPELINE_CONFIG = Variable.get("pipeline_config", deserialize_json=True, default_var={})


# ─── Task Functions ───────────────────────────────────────────────────────────

def check_environment(**context):
    """
    Reads the 'environment' Variable to decide which database to use.
    Shows how to read variables at RUNTIME (inside the task function),
    which avoids the parse-time DB hit.
    """
    # Read at runtime — fresher value, lower parse-time cost
    env = Variable.get("environment", default_var="dev")
    schema = Variable.get("target_schema", default_var="dev_analytics")

    print(f"Running in environment: {env}")
    print(f"Target schema: {schema}")

    # Also check if this run was given a per-run config via the trigger UI
    # dag_run.conf is a dict passed when triggering the DAG manually
    run_conf = context["dag_run"].conf or {}
    override_schema = run_conf.get("schema")  # e.g., passed at trigger time

    if override_schema:
        print(f"Schema overridden by run config: {override_schema}")
        schema = override_schema

    print(f"Final target schema: {schema}")
    return schema  # Return value stored as XCom (covered in Section 09)


def process_data(**context):
    """
    Reads configuration from both Variables and run-time conf.
    Demonstrates combining static config (Variables) with dynamic config (conf).
    """
    # Read the max_records limit from a Variable
    max_records = int(Variable.get("max_records", default_var="10000"))

    # Check for a per-run override
    run_conf = context["dag_run"].conf or {}
    override_limit = run_conf.get("max_records")
    if override_limit:
        max_records = int(override_limit)
        print(f"max_records overridden by run conf: {max_records}")

    logical_date = context["ds"]
    print(f"Processing up to {max_records} records for date: {logical_date}")

    # Simulate processing
    records_processed = min(max_records, 42_000)
    print(f"Processed {records_processed} records")

    return records_processed


def log_summary(**context):
    """
    Prints a run summary. In production, this might write to a metrics table
    or send a structured log to a monitoring system.
    """
    env = Variable.get("environment", default_var="dev")
    run_id = context["run_id"]
    ds = context["ds"]

    print("=" * 60)
    print(f"  PIPELINE SUMMARY")
    print(f"  Environment : {env}")
    print(f"  Logical Date: {ds}")
    print(f"  Run ID      : {run_id}")
    print("=" * 60)


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="example_parametrized_dag",
    description=(
        f"Parametrized pipeline. Current env: {ENVIRONMENT}. "
        "Reads config from Airflow Variables."
    ),
    default_args={
        "owner": "data-team",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
    },
    start_date=datetime(2024, 1, 1),

    # schedule_interval=None means this DAG ONLY runs when manually triggered.
    # It will never run automatically on a schedule.
    schedule_interval=None,

    catchup=False,
    tags=["example", "parametrized", "variables"],

    # params defines the schema for per-run configuration.
    # These show up as a form in the Trigger UI (Airflow 2.2+).
    params={
        "schema": "analytics",        # Which schema to write to
        "max_records": 10000,          # Cap on records to process
    },

) as dag:

    # ── Task 1: Check which environment we are running in ─────────────────────
    check_env = PythonOperator(
        task_id="check_environment",
        python_callable=check_environment,
    )

    # ── Task 2: Print the active Variables using BashOperator ─────────────────
    # Demonstrates reading Airflow Variables inside Jinja templates.
    # {{ var.value.environment }} renders the value of the "environment" Variable.
    print_config = BashOperator(
        task_id="print_config",
        bash_command=(
            "echo 'Environment Variable: {{ var.value.environment }}' && "
            "echo 'Run conf schema: {{ dag_run.conf.get(\"schema\", \"not set\") }}' && "
            "echo 'Logical date: {{ ds }}'"
        ),
    )

    # ── Task 3: Process data with variable-controlled limits ──────────────────
    process = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )

    # ── Task 4: Log the summary ───────────────────────────────────────────────
    summary = PythonOperator(
        task_id="log_summary",
        python_callable=log_summary,
    )

    # ─── Dependencies ─────────────────────────────────────────────────────────
    # Linear flow: check env → print config → process → summary
    check_env >> print_config >> process >> summary
```

---

## How to Run These Examples

### Step 1: Copy the files

```bash
# Copy both files to your dags folder
cp example_etl_dag.py ./dags/
cp example_parametrized_dag.py ./dags/
```

### Step 2: Set variables for the parametrized DAG

```bash
# Via CLI (inside the scheduler container for Docker Compose)
docker compose exec airflow-scheduler airflow variables set environment "development"
docker compose exec airflow-scheduler airflow variables set target_schema "dev_analytics"
docker compose exec airflow-scheduler airflow variables set max_records "5000"

# Or via the UI: Admin → Variables → + Add
```

### Step 3: Trigger the DAGs

```bash
# Trigger example_etl_dag (it will run on schedule, or trigger manually)
docker compose exec airflow-scheduler airflow dags trigger example_etl_dag

# Trigger the parametrized DAG with a custom config
docker compose exec airflow-scheduler airflow dags trigger example_parametrized_dag \
    --conf '{"schema": "test_schema", "max_records": 100}'
```

### Step 4: Test a single task

```bash
# Run just the extract task for a specific date (does not record in DB)
docker compose exec airflow-scheduler \
    airflow tasks test example_etl_dag extract_from_api 2024-01-15
```

---

## 📂 Navigation

⬅️ **Prev:** [Interview Q&A](./Interview_QA.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [04 · Operators](../04_Operators/Theory.md)
