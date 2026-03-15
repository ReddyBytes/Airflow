# FileSensor — Theory

## The Patient Doorman

Your DAG runs every morning at 6am to process files that a vendor drops in a shared folder. The pipeline is ready. The processing logic is written. Everything is set.

But the vendor is sometimes early. Sometimes late. Sometimes they deliver at 5:45am. Sometimes at 9:30am.

What do you do? You could delay your DAG to start later — but then on the days the vendor is early, you waste time. You could poll in a Python loop — but that's messy and hard to monitor.

**FileSensor is Airflow's built-in solution.** It sits at the door of your pipeline like a patient doorman. It checks the filesystem on a regular interval. When the file appears, it lets the pipeline in. If the file never shows up, it eventually gives up and raises the alarm.

---

## What FileSensor Does

`FileSensor` checks whether a file (or directory) exists at the specified path. It calls `os.path.exists()` (or a hook-based equivalent) on each poke.

```python
from airflow.sensors.filesystem import FileSensor

wait_for_delivery = FileSensor(
    task_id="wait_for_vendor_delivery",
    filepath="/data/incoming/vendor_orders_{{ ds_nodash }}.csv",
    fs_conn_id="fs_default",   # Connection to the filesystem
    poke_interval=60,          # Check every 60 seconds
    timeout=4 * 60 * 60,       # Give up after 4 hours
    mode="reschedule",
)
```

When the file exists at `filepath`, `poke()` returns `True` and the sensor succeeds.

---

## The filepath Parameter

Accepts a path string with Jinja templating:

```python
# Static path
filepath="/data/input/orders.csv"

# Dynamic with execution date
filepath="/data/input/orders_{{ ds_nodash }}.csv"
# e.g. → /data/input/orders_20240115.csv

# Wildcard pattern (glob)
filepath="/data/input/orders_*.csv"
# Matches any file starting with "orders_"
```

**Note on wildcards:** FileSensor uses Python's `glob` module. Patterns like `*`, `?`, and `[...]` are supported.

---

## The fs_conn_id Parameter

This tells FileSensor which filesystem connection to use. For local files, use `"fs_default"` (which maps to the local filesystem).

To set up a filesystem connection:
1. Go to **Admin → Connections**
2. Add a connection with type `File (path)` and set the path to the base directory
3. Reference it via `fs_conn_id`

For simple local paths, you often don't need to set up a connection — the default `fs_default` connection works on the local worker filesystem.

---

## Handling File Patterns (Glob)

FileSensor supports glob patterns to wait for files matching a pattern:

```python
# Wait for any CSV file in today's directory
wait_for_any_csv = FileSensor(
    task_id="wait_for_any_csv",
    filepath="/data/incoming/{{ ds }}/*.csv",
    mode="reschedule",
    poke_interval=120,
    timeout=7200,
)

# Wait for file matching a date pattern
wait_for_dated_file = FileSensor(
    task_id="wait_for_dated_file",
    filepath="/data/incoming/report_{{ ds_nodash }}*.csv",
    mode="reschedule",
    poke_interval=60,
)
```

When a glob pattern is used, `poke()` returns `True` as soon as **any** matching file exists.

---

## Full Working Code Example

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.filesystem import FileSensor
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="file_sensor_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 6 * * *",   # Run at 6am daily
    catchup=False,
    default_args={"retries": 1},
) as dag:

    # Wait up to 6 hours for the vendor file to appear
    wait_for_file = FileSensor(
        task_id="wait_for_vendor_file",
        filepath="/data/incoming/vendor_orders_{{ ds_nodash }}.csv",
        fs_conn_id="fs_default",
        poke_interval=60,               # Check every minute
        timeout=6 * 60 * 60,            # Give up after 6 hours
        mode="reschedule",              # Release worker between checks
        soft_fail=False,               # Fail (don't skip) if timeout exceeded
    )

    def process_vendor_file(**context):
        date = context["ds_nodash"]
        filepath = f"/data/incoming/vendor_orders_{date}.csv"
        print(f"Processing file: {filepath}")
        # ... actual processing

    process_file = PythonOperator(
        task_id="process_vendor_file",
        python_callable=process_vendor_file,
    )

    move_to_processed = BashOperator(
        task_id="archive_file",
        bash_command="""
            mkdir -p /data/processed/{{ ds }}
            mv /data/incoming/vendor_orders_{{ ds_nodash }}.csv \
               /data/processed/{{ ds }}/vendor_orders.csv
        """,
    )

    wait_for_file >> process_file >> move_to_processed
```

---

## When to Use FileSensor

**Good for:**
- Waiting for vendor file deliveries
- Waiting for upstream pipelines that write files to disk
- Checking that a mounted network drive has received a file
- Simple "gate" before processing begins

**Not ideal for:**
- Files on S3 (use `S3KeySensor` instead)
- Files on remote SFTP servers (use `SFTPSensor`)
- Monitoring many files (one sensor per file pattern)

---

## Navigation

**Prev:** [Sensors Theory](../Theory.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [HttpSensor Theory](../02_HttpSensor/Theory.md)
