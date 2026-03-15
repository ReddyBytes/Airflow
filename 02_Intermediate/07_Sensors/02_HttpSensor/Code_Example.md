# HttpSensor — Code Examples

## Example 1: Simple Health Check

Wait for a service to be available before the pipeline makes any requests to it.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
import json

with DAG(
    dag_id="http_sensor_health_check",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["sensor", "http", "example"],
) as dag:

    # STEP 1: Basic health check — just check it returns 200
    # No response_check function needed for simple cases
    check_api_health = HttpSensor(
        task_id="check_api_is_up",
        http_conn_id="my_weather_api",
        # Connection host: https://api.openweathermap.org
        endpoint="/data/2.5/weather",
        request_params={
            "q": "London",
            "appid": "{{ var.value.openweather_api_key }}",
        },
        # Default behavior: succeed if HTTP response is 2xx
        # Fail if 4xx or 5xx
        poke_interval=30,         # Check every 30 seconds
        timeout=10 * 60,          # Give up after 10 minutes
        mode="reschedule",
    )

    # STEP 2: After health check passes, fetch the data
    fetch_weather = SimpleHttpOperator(
        task_id="fetch_weather_data",
        http_conn_id="my_weather_api",
        endpoint="/data/2.5/weather",
        method="GET",
        data={
            "q": "London",
            "appid": "{{ var.value.openweather_api_key }}",
            "units": "metric",
        },
        response_filter=lambda response: response.text,
        log_response=True,
    )

    # STEP 3: Process the fetched weather data
    def process_weather(**context):
        ti = context["ti"]
        raw_response = ti.xcom_pull(task_ids="fetch_weather_data")
        data = json.loads(raw_response)

        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        description = data["weather"][0]["description"]

        print(f"London weather for {context['ds']}:")
        print(f"  Temperature: {temp}°C (feels like {feels_like}°C)")
        print(f"  Humidity: {humidity}%")
        print(f"  Conditions: {description}")

        return {"temp": temp, "humidity": humidity, "description": description}

    process = PythonOperator(
        task_id="process_weather_data",
        python_callable=process_weather,
    )

    check_api_health >> fetch_weather >> process
```

---

## Example 2: Check with Custom response_check Function

Use `response_check` when you need to validate more than just the HTTP status code.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.operators.python import PythonOperator
import json


# =============================================================================
# response_check FUNCTIONS
# Define these outside the DAG for cleaner code
# =============================================================================

def check_records_available(response) -> bool:
    """
    Returns True only when:
    1. HTTP status is 200
    2. Response body has status='ready'
    3. record_count is greater than 0
    """
    if response.status_code != 200:
        print(f"Unexpected status code: {response.status_code}")
        return False

    try:
        data = response.json()
    except ValueError:
        print("Response is not valid JSON")
        return False

    status = data.get("status")
    record_count = data.get("record_count", 0)
    processing_complete = data.get("processing_complete", False)

    print(f"API status: {status}, records: {record_count}, complete: {processing_complete}")

    # All three conditions must be true
    return status == "ready" and record_count > 0 and processing_complete


def check_report_generated(response) -> bool:
    """
    Wait for a report generation job to complete.
    The API returns a job status with progress percentage.
    """
    if response.status_code == 202:
        # 202 Accepted = still processing
        try:
            data = response.json()
            progress = data.get("progress_percent", 0)
            print(f"Report still generating... {progress}% complete")
        except Exception:
            print("Job still running")
        return False

    if response.status_code == 200:
        # 200 OK = report is ready
        try:
            data = response.json()
            report_url = data.get("report_url")
            if report_url:
                print(f"Report ready at: {report_url}")
                return True
        except Exception:
            pass

    print(f"Unexpected response: {response.status_code}")
    return False


def check_pipeline_upstream_ready(response) -> bool:
    """
    Check if upstream pipeline has loaded data for today.
    Response: {"tables": {"orders": {"row_count": 1542, "loaded": true}, ...}}
    """
    try:
        data = response.json()
        tables = data.get("tables", {})

        required_tables = ["orders", "customers", "products"]
        for table in required_tables:
            table_info = tables.get(table, {})
            if not table_info.get("loaded", False):
                print(f"Table '{table}' not yet loaded")
                return False
            row_count = table_info.get("row_count", 0)
            if row_count == 0:
                print(f"Table '{table}' is loaded but empty")
                return False
            print(f"Table '{table}': {row_count} rows ✓")

        print("All required tables are loaded and ready")
        return True

    except Exception as e:
        print(f"Error parsing response: {e}")
        return False


# =============================================================================
# DAG DEFINITION
# =============================================================================

with DAG(
    dag_id="http_sensor_response_check",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["sensor", "http", "response-check", "example"],
) as dag:

    # Example A: Wait for data to be available with full validation
    wait_for_data_api = HttpSensor(
        task_id="wait_for_data_availability",
        http_conn_id="my_data_platform_api",
        endpoint="/api/v2/status",
        request_params={
            "date": "{{ ds }}",
            "source": "orders",
        },
        headers={
            "Authorization": "Bearer {{ var.value.data_platform_token }}",
            "Accept": "application/json",
        },
        response_check=check_records_available,
        poke_interval=120,         # Check every 2 minutes
        timeout=6 * 60 * 60,       # Wait up to 6 hours
        mode="reschedule",
    )

    # Example B: Wait for a report generation job to finish
    # (async job pattern: start job in previous task, wait here)
    wait_for_report = HttpSensor(
        task_id="wait_for_report_generation",
        http_conn_id="my_reporting_api",
        endpoint="/reports/{{ var.value.report_job_id }}/status",
        response_check=check_report_generated,
        poke_interval=30,           # Report generates in minutes, check often
        timeout=60 * 60,            # Should finish within 1 hour
        mode="reschedule",
    )

    # Example C: Wait for upstream pipeline tables to be ready
    wait_for_upstream_tables = HttpSensor(
        task_id="wait_for_upstream_tables",
        http_conn_id="my_data_catalog_api",
        endpoint="/api/readiness",
        request_params={"date": "{{ ds }}"},
        response_check=check_pipeline_upstream_ready,
        poke_interval=180,          # Check every 3 minutes
        timeout=4 * 60 * 60,
        mode="reschedule",
        soft_fail=False,            # Hard fail if tables never arrive
    )

    def run_main_pipeline(**context):
        print(f"Upstream data confirmed ready for {context['ds']}")
        print("Running main pipeline logic...")

    run_pipeline = PythonOperator(
        task_id="run_main_pipeline",
        python_callable=run_main_pipeline,
    )

    # Run all three sensors in parallel before the main pipeline
    [wait_for_data_api, wait_for_report, wait_for_upstream_tables] >> run_pipeline
```

**What to notice:**
- `response_check` receives the full `requests.Response` object — use `.json()`, `.text`, `.status_code`, `.headers` etc.
- Return `True` to signal "condition met — task succeeds"
- Return `False` to signal "not ready yet — keep waiting"
- The function can include `print()` statements — they appear in the task logs on each poke
- Define `response_check` functions outside the DAG for readability and testability
- You can write unit tests for these functions independently of Airflow
- `request_params` supports Jinja templates (rendered before the HTTP call)
- Multiple sensors can run in parallel with `[s1, s2, s3] >> next_task`
