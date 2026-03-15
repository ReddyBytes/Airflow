# HttpOperator — Code Examples

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: GET Request to Fetch Data

This example fetches exchange rates from a public API, extracts the data with `response_filter`, and uses it in a downstream task via XCom.

```python
# dags/http_example_01_get.py
import json
from airflow.decorators import dag, task
from airflow.providers.http.operators.http import HttpOperator
from datetime import datetime


@dag(
    dag_id="http_example_01_get",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["http", "example"],
)
def http_example_01_get():
    """
    Example: GET request to an exchange rate API.

    Prerequisites:
    - Connection 'exchange_api' with host: https://open.er-api.com
    - No auth required for this public API

    Create connection:
        airflow connections add 'exchange_api' \
          --conn-type 'http' \
          --conn-host 'https://open.er-api.com'
    """

    # GET /v6/latest/USD?date=2025-03-15
    fetch_rates = HttpOperator(
        task_id="fetch_exchange_rates",
        http_conn_id="exchange_api",
        # endpoint supports Jinja — ds is rendered at runtime
        endpoint="/v6/latest/USD",
        method="GET",
        # Validate: the API must return HTTP 200 and a "success" result
        response_check=lambda response: (
            response.status_code == 200
            and response.json().get("result") == "success"
        ),
        # Extract only the rates dict from the response body
        response_filter=lambda response: response.json()["rates"],
        # Log the raw response to the task log for debugging
        log_response=True,
        # Pass extra kwargs to requests (e.g. timeout)
        extra_options={"timeout": 15},
    )

    @task
    def process_rates(**context):
        """Pull the extracted rates dict and compute EUR/GBP cross rate."""
        # XCom key is "return_value" by default; task_ids matches HttpOperator's task_id
        rates = context["ti"].xcom_pull(task_ids="fetch_exchange_rates")

        if not rates:
            raise ValueError("No rates received from API")

        eur_rate = rates.get("EUR")
        gbp_rate = rates.get("GBP")
        print(f"USD/EUR: {eur_rate}")
        print(f"USD/GBP: {gbp_rate}")

        # Write to a file (in a real pipeline, write to a database or S3)
        output = {
            "date": context["ds"],
            "USD_EUR": eur_rate,
            "USD_GBP": gbp_rate,
        }
        print(f"Saving: {json.dumps(output, indent=2)}")
        return output

    fetch_rates >> process_rates()


http_example_01_get()
```

---

## Example 2: POST Request with JSON Body

This example triggers a model training job via a POST request, extracts the `job_id` from the response, and polls the job status in a subsequent task.

```python
# dags/http_example_02_post.py
import json
from airflow.decorators import dag, task
from airflow.providers.http.operators.http import HttpOperator
from airflow.operators.bash import BashOperator
from datetime import datetime


@dag(
    dag_id="http_example_02_post",
    schedule="@weekly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["http", "example"],
)
def http_example_02_post():
    """
    Example: POST to trigger a training job, then check its status.

    Prerequisites:
    - Connection 'ml_api' with:
        Host: https://ml.example.com
        Extra: {"Authorization": "Bearer YOUR_TOKEN"}

    Create connection:
        airflow connections add 'ml_api' \
          --conn-type 'http' \
          --conn-host 'https://ml.example.com' \
          --conn-extra '{"Authorization": "Bearer sk-abc123"}'
    """

    # Trigger a training job via POST
    trigger_training = HttpOperator(
        task_id="trigger_training_job",
        http_conn_id="ml_api",
        endpoint="/v1/training-jobs",
        method="POST",
        # JSON body — must be a string when Content-Type is application/json
        data=json.dumps({
            "model_name": "fraud_detector_v3",
            "training_date": "{{ ds }}",          # Jinja in data field
            "dataset_path": "s3://ml-data/{{ ds_nodash }}/train.parquet",
            "hyperparams": {
                "learning_rate": 0.001,
                "epochs": 100,
                "batch_size": 256,
            },
        }),
        headers={"Content-Type": "application/json"},
        # Validate: expect HTTP 201 Created
        response_check=lambda r: r.status_code == 201,
        # Extract the job_id from the response for downstream use
        response_filter=lambda r: r.json()["job_id"],
        log_response=True,
        extra_options={"timeout": 30},
    )

    @task
    def wait_for_job(**context):
        """
        Poll the job status endpoint until the job completes.
        In a real pipeline, use an HttpSensor or a deferrable operator instead.
        """
        import time
        import requests

        # Pull job_id from the trigger task's XCom
        job_id = context["ti"].xcom_pull(task_ids="trigger_training_job")
        print(f"Waiting for job: {job_id}")

        # Simulate polling (in production use HttpSensor with deferrable=True)
        for attempt in range(1, 6):
            print(f"Check {attempt}/5 for job {job_id}...")
            # In a real pipeline, you would call:
            # response = requests.get(f"https://ml.example.com/v1/jobs/{job_id}",
            #                         headers={"Authorization": "Bearer sk-abc123"})
            # status = response.json()["status"]
            # if status == "completed": break
            # time.sleep(30)
            time.sleep(1)  # Simulated delay

        print(f"Job {job_id} completed")
        return {"job_id": job_id, "status": "completed"}

    @task
    def register_model(job_result: dict, **context):
        """Register the trained model in the model registry."""
        job_id = job_result["job_id"]
        training_date = context["ds"]
        print(f"Registering model from job {job_id} trained on {training_date}")

    job_result = wait_for_job()
    trigger_training >> job_result
    register_model(job_result)


http_example_02_post()
```

---

## Example 3: `response_check` for Service Validation

This example uses `HttpOperator` as a pre-flight health check before the main pipeline runs. If the external service is unhealthy, the pipeline stops immediately rather than failing deep in processing.

```python
# dags/http_example_03_response_check.py
import json
from airflow.decorators import dag, task
from airflow.providers.http.operators.http import HttpOperator
from datetime import datetime


def check_api_healthy(response) -> bool:
    """
    Custom response_check function.
    Returns True if the API is healthy and ready to accept requests.
    Returns False (causing task failure) if any check fails.
    """
    # Check 1: HTTP status must be 200
    if response.status_code != 200:
        print(f"Unhealthy: HTTP {response.status_code}")
        return False

    # Check 2: Response must be valid JSON
    try:
        body = response.json()
    except ValueError:
        print("Unhealthy: Response is not valid JSON")
        return False

    # Check 3: Service must report itself as healthy
    if body.get("status") != "healthy":
        print(f"Unhealthy: status={body.get('status')}, message={body.get('message')}")
        return False

    # Check 4: No active incidents
    if body.get("active_incidents", 0) > 0:
        print(f"Unhealthy: {body['active_incidents']} active incident(s)")
        return False

    print(f"API healthy. Version: {body.get('version')}, Latency: {body.get('latency_ms')}ms")
    return True


def extract_api_version(response) -> str:
    """Extract API version to pass downstream (for logging/audit)."""
    return response.json().get("version", "unknown")


@dag(
    dag_id="http_example_03_response_check",
    schedule="@hourly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["http", "example"],
)
def http_example_03_response_check():
    """
    Example: Pre-flight health check before running the main pipeline.
    Uses a custom response_check function to validate multiple conditions.

    Prerequisites:
    - Connection 'data_provider_api' configured with base URL
    """

    # Task 1: Verify the external API is healthy
    health_check = HttpOperator(
        task_id="check_data_provider_health",
        http_conn_id="data_provider_api",
        endpoint="/health",
        method="GET",
        # Custom validation function (defined above, outside the DAG)
        response_check=check_api_healthy,
        # Extract API version for downstream logging
        response_filter=extract_api_version,
        log_response=True,
        # Retry up to 3 times with 30s between retries before giving up
        retries=3,
        retry_delay=30,
    )

    # Task 2: Only runs if health check passed
    @task
    def fetch_daily_data(**context):
        api_version = context["ti"].xcom_pull(task_ids="check_data_provider_health")
        ds = context["ds"]
        print(f"Fetching {ds} data from API version {api_version}")
        # ... actual data fetch logic
        return {"records": 1500, "date": ds}

    @task
    def validate_data(fetch_result: dict):
        records = fetch_result["records"]
        if records == 0:
            raise ValueError("No records received — possible upstream issue")
        print(f"Validated {records} records")

    # Task 3: POST to acknowledge receipt (webhook notification)
    ack_webhook = HttpOperator(
        task_id="acknowledge_receipt",
        http_conn_id="data_provider_api",
        endpoint="/webhooks/receipt",
        method="POST",
        data=json.dumps({
            "run_date": "{{ ds }}",
            "run_id": "{{ dag_run.run_id }}",
            "status": "received",
        }),
        headers={"Content-Type": "application/json"},
        # For acknowledgment endpoints, any 2xx is fine
        response_check=lambda r: 200 <= r.status_code < 300,
    )

    fetch_result = fetch_daily_data()
    health_check >> fetch_result
    validate_data(fetch_result) >> ack_webhook


http_example_03_response_check()
```

**Key points demonstrated in Example 3:**
- `response_check` as a named function (not lambda) for complex validation
- Multiple conditions checked in a single `response_check`
- `response_filter` for extracting metadata to pass downstream
- `retries` and `retry_delay` on the operator for transient failures
- Chaining HttpOperator with `@task` functions
