# DAG Params and Runtime Configuration — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Basic String Params with Jinja Access

This is the simplest use case — a DAG with two string params that are injected into a `BashOperator` command via Jinja templates.

```python
# dags/example_01_basic_params.py
from airflow.decorators import dag
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from datetime import datetime


@dag(
    dag_id="example_01_basic_params",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["params", "example"],
    params={
        # Simple string param with a default value
        "source_path": Param(
            "/data/raw/orders",
            type="string",
            description="Source directory containing raw order files",
        ),
        # String param with an enumerated set of valid values
        "output_format": Param(
            "parquet",
            type="string",
            enum=["parquet", "csv", "json"],
            description="Output file format for the processed data",
        ),
    },
)
def example_01_basic_params():
    """
    Demonstrates basic string Params accessed via Jinja {{ params.name }} syntax.
    Try triggering this DAG manually with different output_format values.
    """

    # BashOperator.bash_command is in template_fields, so Jinja renders it
    convert = BashOperator(
        task_id="convert_files",
        bash_command=(
            "python /opt/scripts/convert.py "
            "--source {{ params.source_path }} "
            "--format {{ params.output_format }} "
            "--date {{ ds }}"
        ),
        # The rendered command might look like:
        # python /opt/scripts/convert.py --source /data/raw/orders
        #   --format parquet --date 2025-03-15
    )

    # env dict is also in template_fields for BashOperator
    log_result = BashOperator(
        task_id="log_result",
        bash_command="echo 'Converted {{ ds }} data to {{ params.output_format }}'",
        env={
            "SOURCE": "{{ params.source_path }}",
            "FORMAT": "{{ params.output_format }}",
            "RUN_DATE": "{{ ds }}",
        },
    )

    convert >> log_result


example_01_basic_params()
```

**To run with custom values:**
```bash
airflow dags trigger example_01_basic_params \
  --conf '{"source_path": "/data/raw/returns", "output_format": "csv"}'
```

---

## Example 2: Typed Params with Validation

This example demonstrates integer, boolean, enum, and date-format params — including how validation works and how to handle optional (nullable) params.

```python
# dags/example_02_typed_params.py
from airflow.decorators import dag, task
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from datetime import datetime


@dag(
    dag_id="example_02_typed_params",
    schedule="@weekly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["params", "example"],
    params={
        # Date param — Airflow 3 renders a date picker in the trigger UI
        "start_date": Param(
            "{{ ds }}",
            type="string",
            format="date",
            title="Processing Start Date",
            description="First date to include in the report window",
        ),
        # Integer with min/max validation
        "lookback_days": Param(
            7,
            type="integer",
            minimum=1,
            maximum=365,
            title="Lookback Window (days)",
            description="Number of days to look back from start_date",
        ),
        # Enum dropdown in UI
        "aggregation": Param(
            "daily",
            type="string",
            enum=["hourly", "daily", "weekly", "monthly"],
            description="Time granularity for aggregation",
        ),
        # Boolean toggle
        "include_refunds": Param(
            True,
            type="boolean",
            description="Whether to include refund transactions in the totals",
        ),
        # Optional integer — can be null (no limit)
        "row_limit": Param(
            None,
            type=["integer", "null"],
            minimum=1,
            description="Max rows to process. Leave empty for full dataset.",
        ),
        # Float with range
        "confidence_threshold": Param(
            0.95,
            type="number",
            minimum=0.0,
            maximum=1.0,
            description="Minimum confidence score to include a prediction",
        ),
    },
)
def example_02_typed_params():
    """
    Demonstrates typed Params (integer, boolean, enum, date, float, nullable).
    All validation is enforced at trigger time — invalid values are rejected
    before the DAG run is created.
    """

    @task
    def validate_and_log(**context):
        """Access all params in Python and log them."""
        params = context["params"]

        start = params["start_date"]
        lookback = params["lookback_days"]
        aggregation = params["aggregation"]
        include_refunds = params["include_refunds"]
        row_limit = params["row_limit"]          # May be None
        threshold = params["confidence_threshold"]

        print(f"Processing configuration:")
        print(f"  Start date:    {start}")
        print(f"  Lookback:      {lookback} days")
        print(f"  Aggregation:   {aggregation}")
        print(f"  Refunds:       {'included' if include_refunds else 'excluded'}")
        print(f"  Row limit:     {row_limit if row_limit else 'unlimited'}")
        print(f"  Threshold:     {threshold}")

        # Return config for downstream tasks
        return {
            "start_date": start,
            "lookback_days": lookback,
            "aggregation": aggregation,
        }

    # Jinja conditionals work inside bash_command
    run_report = BashOperator(
        task_id="run_report",
        bash_command=(
            "report_generator.py "
            "--start {{ params.start_date }} "
            "--lookback {{ params.lookback_days }} "
            "--agg {{ params.aggregation }} "
            "{% if params.include_refunds %}--include-refunds {% endif %}"
            "{% if params.row_limit %}--limit {{ params.row_limit }}{% endif %}"
        ),
    )

    config = validate_and_log()
    config >> run_report


example_02_typed_params()
```

**To trigger with all-custom values:**
```bash
airflow dags trigger example_02_typed_params \
  --conf '{
    "start_date": "2024-01-01",
    "lookback_days": 90,
    "aggregation": "monthly",
    "include_refunds": false,
    "row_limit": 10000,
    "confidence_threshold": 0.99
  }'
```

**Validation examples — these will be rejected:**
```bash
# Wrong type for integer field
--conf '{"lookback_days": "thirty"}'  # Error: not an integer

# Value outside enum
--conf '{"aggregation": "quarterly"}' # Error: not in ["hourly","daily","weekly","monthly"]

# Below minimum
--conf '{"lookback_days": 0}'         # Error: minimum is 1
```

---

## Example 3: Complex Conf-Based Dynamic DAG Behavior

This example shows how `dag_run.conf` can drive fundamentally different execution paths — different tasks run depending on what was passed at trigger time.

```python
# dags/example_03_dynamic_behavior.py
from airflow.decorators import dag, task
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime


@dag(
    dag_id="example_03_dynamic_behavior",
    schedule=None,                          # Manual trigger only
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["params", "example", "advanced"],
    params={
        # What kind of operation are we performing?
        "operation": Param(
            "full_load",
            type="string",
            enum=["full_load", "incremental", "validate_only", "backfill"],
            title="Operation Type",
            description="Determines which pipeline branch to execute",
        ),
        # Date range for backfill operations
        "backfill_start": Param(
            None,
            type=["string", "null"],
            format="date",
            description="Start date for backfill (required when operation=backfill)",
        ),
        "backfill_end": Param(
            None,
            type=["string", "null"],
            format="date",
            description="End date for backfill (required when operation=backfill)",
        ),
        # Target table override
        "target_table": Param(
            "analytics.daily_sales",
            type="string",
            description="Destination table (schema.table format)",
        ),
        # Notification list
        "notify_emails": Param(
            [],
            type="array",
            description="Email addresses to notify on completion",
        ),
    },
)
def example_03_dynamic_behavior():
    """
    Demonstrates how params and dag_run.conf can control which tasks run.
    The 'operation' param routes execution to different branches.
    Use schedule=None since this is a manually triggered operational DAG.
    """

    def _choose_branch(**context):
        """Use params to decide which branch to take."""
        operation = context["params"]["operation"]

        branch_map = {
            "full_load":      "run_full_load",
            "incremental":    "run_incremental",
            "validate_only":  "run_validation",
            "backfill":       "run_backfill",
        }
        chosen = branch_map.get(operation, "run_full_load")
        print(f"Operation '{operation}' → branch '{chosen}'")
        return chosen

    branch = BranchPythonOperator(
        task_id="choose_operation_branch",
        python_callable=_choose_branch,
    )

    # Branch 1: Full Load
    full_load = BashOperator(
        task_id="run_full_load",
        bash_command=(
            "load.py full "
            "--target {{ params.target_table }} "
            "--run-id {{ dag_run.run_id }}"
        ),
    )

    # Branch 2: Incremental Load
    incremental = BashOperator(
        task_id="run_incremental",
        bash_command=(
            "load.py incremental "
            "--target {{ params.target_table }} "
            "--since {{ prev_data_interval_start_success or '1970-01-01' }}"
        ),
    )

    # Branch 3: Validate Only
    @task(task_id="run_validation")
    def run_validation(**context):
        table = context["params"]["target_table"]
        run_id = context["dag_run"].run_id
        print(f"Validating {table} for run {run_id}")
        # In a real DAG: run data quality checks, return results
        return {"table": table, "valid": True, "issues": 0}

    # Branch 4: Backfill with date range
    @task(task_id="run_backfill")
    def run_backfill(**context):
        params = context["params"]
        start = params.get("backfill_start")
        end = params.get("backfill_end")

        if not start or not end:
            raise ValueError(
                "backfill_start and backfill_end are required when operation=backfill. "
                f"Got: start={start!r}, end={end!r}"
            )

        print(f"Backfilling {params['target_table']} from {start} to {end}")
        # Simulate processing
        from datetime import date, timedelta
        current = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        days_processed = 0
        while current <= end_date:
            print(f"  Processing {current}")
            current += timedelta(days=1)
            days_processed += 1
        return {"days_processed": days_processed}

    # Join point — all branches converge here
    join = EmptyOperator(
        task_id="join",
        trigger_rule="none_failed_min_one_success",
    )

    # Post-processing: send notifications if configured
    @task(trigger_rule="none_failed_min_one_success")
    def send_notifications(**context):
        params = context["params"]
        emails = params.get("notify_emails", [])
        operation = params["operation"]
        run_id = context["dag_run"].run_id

        if not emails:
            print("No notification emails configured, skipping.")
            return

        for email in emails:
            print(f"Notifying {email}: operation={operation}, run_id={run_id}")

    # Wire up the branches
    validation_task = run_validation()
    backfill_task = run_backfill()

    branch >> [full_load, incremental, validation_task, backfill_task] >> join
    join >> send_notifications()


example_03_dynamic_behavior()
```

**Trigger examples for each branch:**

```bash
# Full load (default)
airflow dags trigger example_03_dynamic_behavior \
  --conf '{"operation": "full_load"}'

# Incremental load
airflow dags trigger example_03_dynamic_behavior \
  --conf '{"operation": "incremental", "target_table": "analytics.hourly_events"}'

# Validation only
airflow dags trigger example_03_dynamic_behavior \
  --conf '{"operation": "validate_only"}'

# Backfill Q1 2024 with notifications
airflow dags trigger example_03_dynamic_behavior \
  --conf '{
    "operation": "backfill",
    "backfill_start": "2024-01-01",
    "backfill_end": "2024-03-31",
    "target_table": "analytics.daily_sales",
    "notify_emails": ["ops@example.com", "data-team@example.com"]
  }'
```
