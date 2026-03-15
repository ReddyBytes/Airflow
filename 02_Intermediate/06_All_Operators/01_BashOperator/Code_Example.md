# BashOperator — Code Examples

## Example 1: Simple Bash Command

The simplest possible use — run a single shell command.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="bash_simple_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["bash", "example"],
) as dag:

    # Print current date and time
    print_date = BashOperator(
        task_id="print_date",
        bash_command="date",
    )

    # Check available disk space
    check_disk = BashOperator(
        task_id="check_disk_space",
        bash_command="df -h /",
    )

    # Create a directory if it doesn't exist
    create_output_dir = BashOperator(
        task_id="create_output_directory",
        bash_command="mkdir -p /tmp/airflow_output/{{ ds }}",
        # {{ ds }} is the execution date in YYYY-MM-DD format
        # Airflow automatically renders Jinja templates in bash_command
    )

    # List files in a directory
    list_files = BashOperator(
        task_id="list_input_files",
        bash_command="ls -la /tmp/airflow_output/",
    )

    # Chain tasks together
    print_date >> check_disk >> create_output_dir >> list_files
```

**What to notice:**
- `bash_command` accepts any valid shell command
- `{{ ds }}` is a Jinja template that Airflow fills in with the execution date
- Tasks chain with `>>` (right-shift operator)

---

## Example 2: Multi-Line Bash with Environment Variables

Use shell scripts with multiple steps and pass environment variables to your commands.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="bash_multiline_env_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    default_args=default_args,
    catchup=False,
    tags=["bash", "example"],
) as dag:

    # Multi-line script with error checking
    download_and_validate = BashOperator(
        task_id="download_and_validate_data",
        bash_command="""
            set -e  # Exit immediately if any command fails

            echo "=== Starting download for date: $PROCESS_DATE ==="

            # Create working directory
            mkdir -p $OUTPUT_DIR/$PROCESS_DATE

            # Download data (simulated with curl)
            curl -s -o $OUTPUT_DIR/$PROCESS_DATE/data.json \
                "https://api.example.com/data?date=$PROCESS_DATE"

            # Check that the file was created and is not empty
            if [ ! -s "$OUTPUT_DIR/$PROCESS_DATE/data.json" ]; then
                echo "ERROR: Downloaded file is empty!"
                exit 1
            fi

            # Count records
            RECORD_COUNT=$(python3 -c "
import json
with open('$OUTPUT_DIR/$PROCESS_DATE/data.json') as f:
    data = json.load(f)
print(len(data))
")

            echo "Downloaded $RECORD_COUNT records"
            echo "=== Download complete ==="
        """,
        env={
            "PROCESS_DATE": "{{ ds }}",          # e.g. 2024-01-15
            "OUTPUT_DIR": "/tmp/airflow_pipeline",
            "API_KEY": "{{ var.value.my_api_key }}",  # Pull from Airflow Variables
        },
        cwd="/tmp",  # Run commands from /tmp directory
        execution_timeout=timedelta(minutes=30),
    )

    # Process the downloaded data
    process_data = BashOperator(
        task_id="process_downloaded_data",
        bash_command="""
            set -e
            echo "Processing data for $PROCESS_DATE..."

            python3 /opt/airflow/scripts/transform.py \
                --input $OUTPUT_DIR/$PROCESS_DATE/data.json \
                --output $OUTPUT_DIR/$PROCESS_DATE/processed.csv \
                --date $PROCESS_DATE

            echo "Processing complete. Output:"
            wc -l $OUTPUT_DIR/$PROCESS_DATE/processed.csv
        """,
        env={
            "PROCESS_DATE": "{{ ds }}",
            "OUTPUT_DIR": "/tmp/airflow_pipeline",
        },
    )

    # Cleanup old data (keep last 7 days)
    cleanup_old_data = BashOperator(
        task_id="cleanup_old_data",
        bash_command="""
            echo "Cleaning up data older than 7 days..."
            find /tmp/airflow_pipeline -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
            echo "Cleanup complete"
        """,
    )

    download_and_validate >> process_data >> cleanup_old_data
```

**What to notice:**
- `set -e` at the top of the script makes the whole script fail if any command fails
- Environment variables are passed via `env` dict and accessed with `$VAR_NAME`
- Jinja templates work inside the `env` dict too
- `execution_timeout` prevents tasks from hanging forever
- `|| true` at the end of `find` prevents failure if no old files exist

---

## Example 3: Bash Script That Pushes to XCom

BashOperator automatically pushes the last line of stdout to XCom. Use this to pass data to downstream tasks.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

with DAG(
    dag_id="bash_xcom_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["bash", "xcom", "example"],
) as dag:

    # Task 1: Count records in a file and push count to XCom
    # BashOperator pushes the LAST LINE of stdout to XCom automatically
    count_records = BashOperator(
        task_id="count_records",
        bash_command="""
            FILE="/tmp/data/input_{{ ds_nodash }}.csv"

            # Check file exists
            if [ ! -f "$FILE" ]; then
                echo "0"  # Return 0 if file not found
                exit 0
            fi

            # Count lines (minus header)
            COUNT=$(( $(wc -l < "$FILE") - 1 ))
            echo "File has $COUNT records" >&2  # This goes to logs only (stderr)
            echo $COUNT  # This is the LAST LINE — goes to XCom
        """,
        # Note: only stdout's last line goes to XCom
        # Use >&2 for logging (goes to stderr / task logs)
    )

    # Task 2: Get a database record count
    get_db_count = BashOperator(
        task_id="get_db_record_count",
        bash_command="""
            # Query postgres via psql CLI
            COUNT=$(psql postgresql://user:pass@localhost/mydb \
                -t -c "SELECT COUNT(*) FROM processed_data WHERE date = '$PROCESS_DATE'" \
                | tr -d ' ')
            echo "DB has $COUNT records for $PROCESS_DATE" >&2
            echo $COUNT  # Last line → XCom
        """,
        env={"PROCESS_DATE": "{{ ds }}"},
    )

    # Task 3: Python task that pulls XCom values from both bash tasks
    def validate_counts(**context):
        ti = context["ti"]

        # Pull XCom values from upstream bash tasks
        file_count = ti.xcom_pull(task_ids="count_records")
        db_count = ti.xcom_pull(task_ids="get_db_record_count")

        print(f"File count: {file_count}")
        print(f"DB count: {db_count}")

        # Convert to int (XCom values come back as strings from BashOperator)
        file_count_int = int(file_count) if file_count else 0
        db_count_int = int(db_count) if db_count else 0

        if file_count_int != db_count_int:
            raise ValueError(
                f"Count mismatch! File: {file_count_int}, DB: {db_count_int}"
            )

        print(f"Validation passed: {file_count_int} records in both file and DB")

    validate = PythonOperator(
        task_id="validate_record_counts",
        python_callable=validate_counts,
    )

    # Task 4: Generate a summary report using the counts from XCom
    generate_report = BashOperator(
        task_id="generate_summary",
        bash_command="""
            echo "=== Pipeline Summary for {{ ds }} ==="
            echo "Records processed: {{ ti.xcom_pull(task_ids='count_records') }}"
            echo "Records in DB: {{ ti.xcom_pull(task_ids='get_db_record_count') }}"
            echo "Status: SUCCESS"
            echo "Report saved to /tmp/reports/{{ ds }}.txt"
        """,
        # You can also use Jinja to access XCom directly in bash_command!
    )

    [count_records, get_db_count] >> validate >> generate_report
```

**What to notice:**
- The **last line of stdout** is what gets pushed to XCom — use `echo $COUNT` as the final output
- Use `>&2` (stderr) for any log messages you don't want captured as the XCom value
- In Python tasks, use `ti.xcom_pull(task_ids="bash_task_id")` to retrieve the value
- XCom values from BashOperator come back as **strings** — cast them if needed
- You can also use Jinja `{{ ti.xcom_pull(...) }}` directly inside `bash_command`
