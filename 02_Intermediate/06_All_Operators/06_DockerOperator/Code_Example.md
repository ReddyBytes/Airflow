# DockerOperator — Code Examples

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Run a Python Script in a Custom Docker Image

This example runs a Python data processing script that has dependencies incompatible with the Airflow environment. The script lives inside a custom Docker image built by the data team.

```python
# dags/docker_example_01_python_script.py
from airflow.decorators import dag, task
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount
from datetime import datetime


@dag(
    dag_id="docker_example_01_python_script",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["docker", "example"],
)
def docker_example_01_python_script():
    """
    Demonstrates running a Python script in an isolated Docker container.

    The Docker image 'data-team/etl-processor:2.1.0' contains:
    - Python 3.11
    - pandas 2.1, numpy 1.26, scipy 1.11
    - Custom company libraries

    None of these need to be installed in the Airflow environment.

    Prerequisites:
    - Docker running on the Airflow worker
    - Image 'data-team/etl-processor:2.1.0' available locally or in a registry
    """

    # Step 1: Use a standard image to prepare the input directory
    @task
    def prepare_input(**context):
        import os
        run_dir = f"/opt/airflow/data/runs/{context['ds_nodash']}"
        os.makedirs(run_dir, exist_ok=True)
        # Write a config file the container will read
        config = {
            "processing_date": context["ds"],
            "run_id": context["dag_run"].run_id,
        }
        import json
        with open(f"{run_dir}/config.json", "w") as f:
            json.dump(config, f)
        print(f"Prepared input directory: {run_dir}")
        return run_dir

    # Step 2: Run the actual processing in an isolated container
    run_processor = DockerOperator(
        task_id="run_data_processor",
        # Use a pinned tag for reproducibility — never use 'latest' in production
        image="data-team/etl-processor:2.1.0",
        # Command to execute inside the container
        command="python /app/process_sales.py --date {{ ds }} --config /data/config.json",
        # Environment variables passed into the container
        environment={
            "PROCESSING_DATE": "{{ ds }}",
            "RUN_ID": "{{ dag_run.run_id }}",
            "LOG_LEVEL": "INFO",
            # Retrieve secrets from Airflow Variables or Secrets Backend
            "DB_HOST": "postgres.internal.example.com",
            "DB_PORT": "5432",
        },
        # Mount the data directory (host path : container path : mode)
        volumes=[
            "/opt/airflow/data/runs/{{ ds_nodash }}:/data:rw",
            "/opt/airflow/data/output:/output:rw",
            "/opt/airflow/scripts:/app/scripts:ro",  # Read-only scripts
        ],
        # Working directory inside the container
        working_dir="/app",
        # Remove container after it finishes (keeps things clean)
        auto_remove="force",
        # Always use local Docker daemon
        docker_conn_id="docker_default",
        # Log all container output to the Airflow task log
        # (default behavior — container stdout/stderr is streamed)
        # Retry: try up to 2 times if the container fails
        retries=2,
    )

    # Step 3: Validate the output after the container finishes
    @task
    def validate_output(**context):
        import os
        import json

        output_path = f"/opt/airflow/data/output/{context['ds_nodash']}_summary.json"

        if not os.path.exists(output_path):
            raise FileNotFoundError(
                f"Container did not produce expected output: {output_path}"
            )

        with open(output_path) as f:
            summary = json.load(f)

        print(f"Processing summary: {summary}")
        expected_keys = {"records_processed", "errors", "output_path"}
        missing = expected_keys - set(summary.keys())
        if missing:
            raise ValueError(f"Output missing keys: {missing}")

        print(f"Validation passed: {summary['records_processed']} records processed")
        return summary

    input_dir = prepare_input()
    input_dir >> run_processor >> validate_output()


docker_example_01_python_script()
```

---

## Example 2: Data Processing with Volume Mounts and Resource Limits

This example demonstrates a more production-ready setup: a resource-intensive data transformation job running in a container with explicit CPU/memory limits, multiple volume mounts, and output retrieval via XCom.

```python
# dags/docker_example_02_data_processing.py
import json
from airflow.decorators import dag, task
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime


@dag(
    dag_id="docker_example_02_data_processing",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["docker", "example"],
)
def docker_example_02_data_processing():
    """
    Demonstrates Docker with resource limits, volume mounts, and XCom output.

    Use case: A Spark-like data transformation that needs:
    - Exact pandas/numpy versions pinned
    - 2 CPUs and 4GB RAM
    - Access to raw data files on the host
    - A return value (record count) for downstream tasks
    """

    @task
    def get_input_files(**context) -> list:
        """Simulate discovering input files to process."""
        import os
        date = context["ds_nodash"]
        # In a real pipeline, these would be actual files
        files = [
            f"/opt/airflow/data/raw/sales_{date}_part1.parquet",
            f"/opt/airflow/data/raw/sales_{date}_part2.parquet",
        ]
        print(f"Found {len(files)} input files for {context['ds']}")
        return files

    # Write a job manifest the container will read
    @task
    def write_job_manifest(input_files: list, **context) -> str:
        import os

        manifest_dir = f"/opt/airflow/data/manifests/{context['ds_nodash']}"
        os.makedirs(manifest_dir, exist_ok=True)

        manifest = {
            "job_id": context["dag_run"].run_id,
            "processing_date": context["ds"],
            "input_files": input_files,
            "output_dir": f"/opt/airflow/data/processed/{context['ds_nodash']}",
            "partition_cols": ["region", "product_category"],
        }

        manifest_path = f"{manifest_dir}/job.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"Wrote manifest to {manifest_path}")
        return manifest_dir

    # Run the heavy transformation in Docker with resource limits
    # retrieve_output=True makes the last line of stdout available as XCom
    transform = DockerOperator(
        task_id="transform_sales_data",
        image="data-team/spark-transform:3.5-python311",
        # Pass the manifest directory and date as command arguments
        command=[
            "python",
            "/app/transform.py",
            "--manifest", "/manifests/job.json",
            "--date", "{{ ds }}",
            "--output", "/output",
        ],
        environment={
            "PYTHONPATH": "/app",
            "LOG_LEVEL": "WARNING",
            "ENABLE_PROFILING": "false",
            # Secrets via environment (in production, use Airflow secrets backend)
            "AWS_ACCESS_KEY_ID": "{{ var.value.aws_access_key_id }}",
            "AWS_SECRET_ACCESS_KEY": "{{ var.value.aws_secret_access_key }}",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
        volumes=[
            # Input data (read-only — container should not modify raw data)
            "/opt/airflow/data/raw:/raw:ro",
            # Job manifest directory (created by write_job_manifest task)
            "/opt/airflow/data/manifests/{{ ds_nodash }}:/manifests:ro",
            # Output directory (read-write — container writes results here)
            "/opt/airflow/data/processed/{{ ds_nodash }}:/output:rw",
            # Shared reference data (read-only lookup tables, etc.)
            "/opt/airflow/data/reference:/reference:ro",
        ],
        # Resource constraints
        mem_limit="4g",         # Hard memory limit: 4 GB
        cpus=2.0,               # Allocate 2 CPUs
        # Capture the last line of stdout as an XCom value
        # The transform script should print a JSON summary as its last line
        retrieve_output=True,
        retrieve_output_path="/output/summary.json",
        # Remove the container after it finishes
        auto_remove="force",
        # Pull the image only if it is not already present locally
        # (set to True in CI/CD to always get latest)
        force_pull=False,
        # Give the container up to 30 minutes before killing it
        extra_options={"timeout": 1800},
        retries=1,
    )

    @task
    def process_transform_output(**context):
        """
        Process the XCom output from the DockerOperator.
        retrieve_output=True makes the container's /output/summary.json
        available via XCom.
        """
        # The DockerOperator pushes the file content as a string
        raw_output = context["ti"].xcom_pull(task_ids="transform_sales_data")

        if not raw_output:
            raise ValueError("DockerOperator produced no XCom output")

        summary = json.loads(raw_output)
        print(f"Transform complete:")
        print(f"  Records processed: {summary.get('records_in')}")
        print(f"  Records output:    {summary.get('records_out')}")
        print(f"  Duration:          {summary.get('duration_seconds')}s")
        print(f"  Output path:       {summary.get('output_path')}")

        # Fail the pipeline if the record count looks wrong
        if summary.get("records_out", 0) == 0:
            raise ValueError("Transformation produced zero output records")

        return summary

    @task
    def upload_to_data_warehouse(summary: dict, **context):
        """Load the processed Parquet files into the data warehouse."""
        output_dir = summary.get("output_path", f"/opt/airflow/data/processed/{context['ds_nodash']}")
        print(f"Loading {output_dir} into data warehouse for {context['ds']}")
        # In a real pipeline: use BigQueryInsertJobOperator, SnowflakeOperator, etc.
        return {"loaded": True, "date": context["ds"]}

    # Wire everything together
    input_files = get_input_files()
    manifest_dir = write_job_manifest(input_files)
    manifest_dir >> transform
    summary = process_transform_output()
    transform >> summary
    upload_to_data_warehouse(summary)


docker_example_02_data_processing()
```

**Key patterns demonstrated:**
- `volumes` with Jinja templating for date-stamped paths
- `mem_limit` and `cpus` for resource governance
- `retrieve_output=True` and `retrieve_output_path` for XCom from container
- Separating preparation tasks (`@task`) from the container task (`DockerOperator`)
- `command` as a list (avoids shell injection vs. string form)
- `auto_remove="force"` for clean production operation
