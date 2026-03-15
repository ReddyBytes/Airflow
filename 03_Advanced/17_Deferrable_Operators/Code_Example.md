# 17 — Deferrable Operators: Code Examples

---

## Example 1: Using TimeDeltaSensorAsync (Deferrable Time Wait)

Drop-in replacement for `TimeDeltaSensor` that doesn't block a worker slot during the wait.

```python
from airflow import DAG
from airflow.sensors.time_delta import TimeDeltaSensorAsync
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import logging


def prepare_data(**context):
    logging.info("Preparing data batch...")

def process_data(**context):
    logging.info("Processing data after the wait period.")


with DAG(
    dag_id="deferrable_time_wait",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    tags=["example", "deferrable"],
) as dag:

    prepare = PythonOperator(
        task_id="prepare_data",
        python_callable=prepare_data,
    )

    # TimeDeltaSensorAsync defers instead of blocking a worker
    # The task enters DEFERRED state and the worker is released
    wait = TimeDeltaSensorAsync(
        task_id="wait_5_minutes",
        delta=timedelta(minutes=5),
    )

    process = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )

    prepare >> wait >> process
```

**What happens:**
1. `prepare_data` runs on a worker.
2. `wait_5_minutes` starts, calls `self.defer()` immediately, and releases its worker slot. The task enters `DEFERRED` state.
3. After 5 minutes, the Triggerer fires a `TriggerEvent`.
4. `wait_5_minutes` resumes briefly on a worker, then completes.
5. `process_data` runs.

Compare to `TimeDeltaSensor` — the async version frees the worker for the full 5 minutes.

---

## Example 2: Using S3KeySensorAsync

Wait for a file to appear on S3 without blocking workers.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensorAsync
from datetime import datetime, timedelta
import logging


def process_arrived_file(**context):
    # The file is now confirmed to exist on S3
    bucket = "my-data-bucket"
    key    = f"incoming/{{ ds }}/data.csv"
    logging.info(f"File confirmed on S3: s3://{bucket}/{key}")
    logging.info("Starting ETL processing...")


with DAG(
    dag_id="wait_for_s3_file_deferrable",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "deferrable", "s3"],
) as dag:

    wait_for_file = S3KeySensorAsync(
        task_id="wait_for_daily_data_file",
        bucket_name="my-data-bucket",
        bucket_key="incoming/{{ ds }}/data.csv",
        aws_conn_id="aws_default",
        # How often the Triggerer checks S3 (async, no worker needed)
        poke_interval=60,
        # Fail the task if file doesn't appear within 4 hours
        timeout=timedelta(hours=4).total_seconds(),
        mode="reschedule",   # Not needed with async, but kept for clarity
    )

    process = PythonOperator(
        task_id="process_arrived_file",
        python_callable=process_arrived_file,
    )

    wait_for_file >> process
```

**Key point:** With `S3KeySensorAsync`, the Triggerer uses async boto3 calls to check S3 every `poke_interval` seconds. No worker is occupied during the wait. If you have 50 daily files from 50 partners, all 50 sensors run concurrently in the Triggerer without consuming any worker slots.

---

## Example 3: Building a Custom Deferrable Operator

A custom operator that submits a job to an external system and waits for it to complete — deferring during the wait.

```python
import asyncio
from datetime import timedelta

from airflow.models import BaseOperator
from airflow.triggers.base import BaseTrigger, TriggerEvent
from airflow.utils.context import Context


# ── Step 1: Define the Trigger ──────────────────────────────────────────────

class JobStatusTrigger(BaseTrigger):
    """
    Async trigger that polls a hypothetical job API until
    the job reaches a terminal state (SUCCESS or FAILED).
    """

    def __init__(self, job_id: str, poll_interval: int = 30):
        super().__init__()
        self.job_id       = job_id
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict]:
        """
        Required: return (importable_path, init_kwargs).
        Used to re-create this trigger after a Triggerer restart.
        """
        return (
            "my_dags.triggers.JobStatusTrigger",
            {
                "job_id":        self.job_id,
                "poll_interval": self.poll_interval,
            },
        )

    async def run(self):
        """
        Async generator: polls until terminal state, then yields TriggerEvent.
        IMPORTANT: use asyncio.sleep(), not time.sleep() — blocking defeats deferral.
        """
        import aiohttp  # async HTTP client

        api_url = f"https://jobs.example.com/api/jobs/{self.job_id}/status"

        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(api_url) as resp:
                    data = await resp.json()
                    status = data.get("status")

                if status == "SUCCESS":
                    yield TriggerEvent({"status": "SUCCESS", "job_id": self.job_id})
                    return
                elif status == "FAILED":
                    yield TriggerEvent({"status": "FAILED",  "job_id": self.job_id})
                    return
                # Still running — sleep and check again (non-blocking)
                await asyncio.sleep(self.poll_interval)


# ── Step 2: Define the Deferrable Operator ──────────────────────────────────

class SubmitAndWaitOperator(BaseOperator):
    """
    Submits a job to an external system, then defers until the job completes.
    Worker is only occupied for the brief submission and completion steps.
    """

    def __init__(self, job_config: dict, poll_interval: int = 30, **kwargs):
        super().__init__(**kwargs)
        self.job_config    = job_config
        self.poll_interval = poll_interval

    def execute(self, context: Context):
        import requests  # Regular requests is fine here — submission is fast

        self.log.info(f"Submitting job with config: {self.job_config}")
        response = requests.post(
            "https://jobs.example.com/api/jobs",
            json=self.job_config,
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]
        self.log.info(f"Job submitted. job_id={job_id}. Deferring to Triggerer...")

        # Defer — releases worker slot. Triggerer takes over.
        self.defer(
            trigger=JobStatusTrigger(
                job_id=job_id,
                poll_interval=self.poll_interval,
            ),
            method_name="execute_complete",
            timeout=timedelta(hours=6),   # Fail if job takes more than 6 hours
        )

    def execute_complete(self, context: Context, event: dict):
        """
        Called by Airflow when the trigger yields a TriggerEvent.
        At this point we're back on a worker — execute normally.
        """
        job_id = event["job_id"]
        status = event["status"]
        self.log.info(f"Job {job_id} finished with status: {status}")

        if status == "FAILED":
            raise RuntimeError(f"Job {job_id} failed in the external system.")

        self.log.info(f"Job {job_id} completed successfully.")
        return job_id


# ── Step 3: Use it in a DAG ─────────────────────────────────────────────────

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import logging


def post_process(**context):
    job_id = context["ti"].xcom_pull(task_ids="run_etl_job")
    logging.info(f"Post-processing for job: {job_id}")


with DAG(
    dag_id="custom_deferrable_operator",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "deferrable", "custom"],
) as dag:

    run_job = SubmitAndWaitOperator(
        task_id="run_etl_job",
        job_config={
            "name":   "daily_etl",
            "input":  "s3://raw/{{ ds }}/",
            "output": "s3://processed/{{ ds }}/",
        },
        poll_interval=60,
        retries=1,
    )

    post = PythonOperator(
        task_id="post_process",
        python_callable=post_process,
    )

    run_job >> post
```

**Timeline for this DAG:**
1. `run_etl_job.execute()` runs — submits the job (fast, seconds).
2. `run_etl_job` calls `self.defer()` — worker slot released, task enters `DEFERRED`.
3. `JobStatusTrigger.run()` polls every 60s inside the Triggerer (no worker used).
4. When the job completes, trigger yields `TriggerEvent`.
5. `run_etl_job.execute_complete()` runs briefly on a worker.
6. `post_process` runs.

---

## Navigation

**Prev:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [18 — Callbacks and SLAs](../18_Callbacks_and_SLAs/Code_Example.md)
