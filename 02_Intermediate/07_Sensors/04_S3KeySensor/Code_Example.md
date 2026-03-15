# S3KeySensor — Code Examples

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Wait for a Specific S3 Key

This example builds a complete pipeline that waits for a vendor-delivered CSV file, then processes it.

```python
# dags/s3_sensor_example_01_specific_key.py
from airflow.decorators import dag, task
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.operators.s3 import S3CopyObjectOperator
from datetime import datetime


@dag(
    dag_id="s3_sensor_example_01_specific_key",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["s3", "sensor", "example"],
)
def s3_sensor_example_01_specific_key():
    """
    Wait for a daily vendor delivery file to appear in S3, then process it.

    The vendor uploads a file like: s3://vendor-landing/daily/2025-03-15/sales.csv
    We can't know exactly when it arrives — could be anywhere from 6 AM to 10 AM.

    Prerequisites:
    - AWS Connection 'vendor_aws' configured with access to vendor-landing bucket
    - AWS Connection 'aws_default' configured with access to our data lake bucket
    """

    # Step 1: Wait for the vendor file to appear
    # mode="reschedule" releases the worker slot between checks — more efficient
    # than mode="poke" which blocks a worker for the entire wait duration
    wait_for_vendor_file = S3KeySensor(
        task_id="wait_for_vendor_delivery",
        # Full S3 URI with Jinja — ds is rendered to the run's data interval start date
        bucket_key="s3://vendor-landing/daily/{{ ds }}/sales.csv",
        # AWS connection to use for credential resolution
        aws_conn_id="vendor_aws",
        # Check every 5 minutes (300 seconds)
        poke_interval=300,
        # Give up after 8 hours — sends alert if file never arrives
        timeout=28800,
        # reschedule: between checks, release the worker slot for other tasks
        mode="reschedule",
        # In Airflow 3 with a triggerer component: use deferrable for maximum efficiency
        deferrable=True,
    )

    # Step 2: Archive the raw file to our data lake before processing
    # (preserves the original in case we need to reprocess)
    archive_raw = S3CopyObjectOperator(
        task_id="archive_raw_file",
        source_bucket_key="vendor-landing/daily/{{ ds }}/sales.csv",
        source_bucket_name="vendor-landing",
        dest_bucket_key="raw/vendor/sales/year={{ data_interval_start.year }}/month={{ '%02d' % data_interval_start.month }}/day={{ '%02d' % data_interval_start.day }}/sales.csv",
        dest_bucket_name="company-data-lake",
        aws_conn_id="aws_default",
        source_version_id=None,
    )

    # Step 3: Process the file
    @task
    def process_vendor_file(**context):
        """
        Download and process the vendor CSV.
        In a real pipeline this might use PandasOperator, SparkSubmitOperator,
        or a PythonOperator that reads from S3 using boto3.
        """
        import boto3
        import csv
        import io

        ds = context["ds"]
        s3_key = f"vendor-landing/daily/{ds}/sales.csv"
        bucket = "vendor-landing"

        print(f"Processing s3://{bucket}/{s3_key}")

        # Connect to S3 using the hook (respects Airflow's connection config)
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook
        hook = S3Hook(aws_conn_id="vendor_aws")
        content = hook.read_key(key=s3_key, bucket_name=bucket)

        # Parse the CSV
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        print(f"Loaded {len(rows)} rows from vendor file")

        # Validate required columns
        required_cols = {"order_id", "product_id", "quantity", "amount", "region"}
        actual_cols = set(rows[0].keys()) if rows else set()
        missing = required_cols - actual_cols
        if missing:
            raise ValueError(f"Vendor file missing required columns: {missing}")

        print(f"Validation passed. Columns: {actual_cols}")
        return {"row_count": len(rows), "date": ds}

    # Step 4: Signal completion to downstream systems
    @task
    def signal_ready(result: dict, **context):
        """Write a _SUCCESS marker to indicate processing is complete."""
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook

        hook = S3Hook(aws_conn_id="aws_default")
        marker_key = f"processed/vendor/sales/{ context['ds_nodash'] }/_SUCCESS"

        # Write an empty success marker (common convention)
        hook.load_string(
            string_data="",
            key=marker_key,
            bucket_name="company-data-lake",
            replace=True,
        )
        print(f"Written success marker: s3://company-data-lake/{marker_key}")
        print(f"Total rows processed: {result['row_count']}")

    result = process_vendor_file()
    wait_for_vendor_file >> archive_raw >> result
    signal_ready(result)


s3_sensor_example_01_specific_key()
```

---

## Example 2: Wildcard Pattern with Deferrable Mode

This example waits for multiple Parquet part files from a Spark job (where you don't know in advance how many part files will be written), then loads them all into a data warehouse.

```python
# dags/s3_sensor_example_02_wildcard_deferrable.py
from airflow.decorators import dag, task
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from datetime import datetime


@dag(
    dag_id="s3_sensor_example_02_wildcard_deferrable",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["s3", "sensor", "example"],
)
def s3_sensor_example_02_wildcard_deferrable():
    """
    Wait for Spark output files using wildcard matching, with deferrable mode.

    A Spark job writes:
    - s3://data-lake/spark-output/2025-03-15/part-00000-abc.parquet
    - s3://data-lake/spark-output/2025-03-15/part-00001-abc.parquet
    - s3://data-lake/spark-output/2025-03-15/_SUCCESS
    (number of part files depends on Spark's parallelism)

    Strategy: wait for _SUCCESS marker first, then list and load all parts.
    """

    # Strategy A: Wait for the Spark _SUCCESS marker
    # The Spark job writes _SUCCESS only after ALL part files are written
    # This is safer than wildcarding part files, which might catch in-progress writes
    wait_for_success_marker = S3KeySensor(
        task_id="wait_for_spark_success",
        # Exact match on the _SUCCESS file
        bucket_key="spark-output/{{ ds }}/_SUCCESS",
        bucket_name="data-lake",
        aws_conn_id="aws_default",
        # Check every 2 minutes
        poke_interval=120,
        # Wait up to 4 hours for Spark job to complete
        timeout=14400,
        # Deferrable: zero worker slot consumption while waiting
        # Requires a triggerer component (standard in Airflow 3 production setups)
        deferrable=True,
    )

    # Strategy B: Wildcard match — wait for any Parquet part file
    # Use this when there is no _SUCCESS marker (some tools don't write one)
    wait_for_any_part_file = S3KeySensor(
        task_id="wait_for_any_parquet_part",
        # Wildcard: matches any file starting with 'part-' and ending with '.parquet'
        bucket_key="spark-output/{{ ds }}/part-*.parquet",
        bucket_name="data-lake",
        # REQUIRED when using wildcards
        wildcard_match=True,
        aws_conn_id="aws_default",
        poke_interval=60,
        timeout=14400,
        deferrable=True,
    )

    @task
    def list_all_part_files(**context) -> list:
        """
        After the _SUCCESS marker appears, list all part files for this date.
        Returns a list of S3 keys to load.
        """
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook

        hook = S3Hook(aws_conn_id="aws_default")
        prefix = f"spark-output/{context['ds']}/"

        # List all objects under the prefix
        keys = hook.list_keys(
            bucket_name="data-lake",
            prefix=prefix,
        )

        # Filter to only Parquet files (exclude _SUCCESS, _metadata, etc.)
        parquet_keys = [k for k in (keys or []) if k.endswith(".parquet")]

        print(f"Found {len(parquet_keys)} Parquet files for {context['ds']}:")
        for key in parquet_keys:
            print(f"  s3://data-lake/{key}")

        if not parquet_keys:
            raise ValueError(
                f"No Parquet files found at s3://data-lake/{prefix} "
                "even though _SUCCESS marker exists"
            )

        return parquet_keys

    @task
    def load_to_warehouse(parquet_keys: list, **context) -> dict:
        """
        Load all part files into the data warehouse.
        In a real pipeline: use BigQueryInsertJobOperator, SnowflakeOperator, etc.
        """
        ds = context["ds"]
        print(f"Loading {len(parquet_keys)} files for {ds} into warehouse")

        # Simulate loading
        total_rows = 0
        for key in parquet_keys:
            # In production: use a warehouse-specific operator or boto3 + connector
            rows_in_file = 50000  # Simulated
            total_rows += rows_in_file
            print(f"  Loaded {key}: {rows_in_file:,} rows")

        print(f"Total rows loaded: {total_rows:,}")
        return {"date": ds, "files_loaded": len(parquet_keys), "total_rows": total_rows}

    @task
    def validate_load(load_result: dict, **context):
        """Run post-load data quality checks."""
        ds = context["ds"]
        total_rows = load_result["total_rows"]

        print(f"Validating {ds} load: {total_rows:,} rows in {load_result['files_loaded']} files")

        # Example threshold: expect at least 100k rows for a normal business day
        # (skip this check on weekends)
        from datetime import date
        run_date = date.fromisoformat(ds)
        is_weekday = run_date.weekday() < 5

        if is_weekday and total_rows < 100000:
            raise ValueError(
                f"Row count {total_rows:,} is below the weekday threshold of 100,000. "
                "Possible upstream data issue."
            )

        print(f"Validation passed for {ds}")

    # Wire up the pipeline
    # Using Strategy A (wait for _SUCCESS, then list files)
    # Strategy B (wait_for_any_part_file) would be an alternative first step
    part_files = list_all_part_files()
    wait_for_success_marker >> part_files

    load_result = load_to_warehouse(part_files)
    validate_load(load_result)

    # Strategy B is wired separately (in this example it runs in parallel as a demo)
    # In a real pipeline you would use either A or B, not both
    wait_for_any_part_file  # Shows it is defined but not connected to main chain


s3_sensor_example_02_wildcard_deferrable()
```

**Key patterns demonstrated:**
- `deferrable=True` for efficient waiting with zero worker slot usage
- `wildcard_match=True` for matching unknown filenames
- The `_SUCCESS` marker pattern from Spark/Hadoop ecosystems
- Using `S3Hook.list_keys()` after the sensor to enumerate actual files
- Row count validation as a post-load quality gate
- Handling weekday vs weekend differently based on `pendulum` day-of-week
