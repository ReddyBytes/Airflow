# Event-Driven Scheduling — Code Examples

## Navigation
⬅️ **Prev: [Edge Executor](../34_Edge_Executor/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Object Storage](../36_Object_Storage/Theory.md)**

---

## Example 1: Webhook-Triggered DAG via REST API

A production-grade setup where an S3 file upload event triggers an Airflow DAG. Includes the external webhook handler, the Airflow DAG, authentication, and error handling.

### Part A: The Airflow DAG (event-triggered, no schedule)

```python
# dags/process_customer_upload.py
from airflow import DAG
from airflow.decorators import task
from airflow.operators.python import BranchPythonOperator
from datetime import datetime
from typing import Optional

with DAG(
    dag_id="process_customer_upload",
    start_date=datetime(2024, 1, 1),
    schedule=None,        # Only triggered by external events
    catchup=False,
    tags=["event-driven", "s3", "customers"],
    params={
        "bucket": "uploads-bucket",
        "key": "",
        "file_type": "csv",
        "source_system": "unknown",
    },
) as dag:

    @task
    def validate_input(**context) -> dict:
        """Validate the event payload from the webhook."""
        conf = context["dag_run"].conf or {}

        required_fields = ["bucket", "key"]
        missing = [f for f in required_fields if not conf.get(f)]
        if missing:
            raise ValueError(f"Missing required fields in conf: {missing}")

        file_key: str = conf["key"]
        bucket: str = conf["bucket"]
        file_type: str = conf.get("file_type", "unknown")

        print(f"Event received: s3://{bucket}/{file_key} (type: {file_type})")
        print(f"Trigger run_id: {context['run_id']}")
        print(f"Triggered at: {context['logical_date']}")

        return {
            "bucket": bucket,
            "key": file_key,
            "file_type": file_type,
            "source_system": conf.get("source_system", "unknown"),
        }

    @task
    def download_and_parse(file_info: dict) -> dict:
        """Download the file from S3 and parse it."""
        from airflow.io.path import ObjectStoragePath

        path = ObjectStoragePath(
            f"s3://{file_info['bucket']}/{file_info['key']}",
            conn_id="aws_default",
        )

        print(f"Reading from: {path}")
        # content = path.read_bytes()
        # df = pd.read_csv(io.BytesIO(content))

        # Simulated parsing
        return {
            "row_count": 5420,
            "columns": ["customer_id", "name", "email", "signup_date"],
            "file_size_bytes": 284920,
        }

    @task
    def validate_schema(file_info: dict, parse_result: dict) -> bool:
        """Validate the file matches expected schema."""
        expected_columns = {"customer_id", "name", "email", "signup_date"}
        actual_columns = set(parse_result["columns"])

        if not expected_columns.issubset(actual_columns):
            missing_cols = expected_columns - actual_columns
            raise ValueError(f"Schema validation failed. Missing columns: {missing_cols}")

        print(f"Schema valid. {parse_result['row_count']} rows, {parse_result['file_size_bytes']} bytes")
        return True

    @task
    def load_to_warehouse(file_info: dict, parse_result: dict, schema_valid: bool):
        """Load validated data into the warehouse."""
        print(f"Loading {parse_result['row_count']} rows to warehouse")
        print(f"Source: s3://{file_info['bucket']}/{file_info['key']}")
        # INSERT or MERGE into warehouse table

    @task
    def send_success_notification(file_info: dict, parse_result: dict):
        """Notify stakeholders of successful processing."""
        print(f"SUCCESS: Processed {parse_result['row_count']} customer records")
        print(f"Source system: {file_info['source_system']}")
        # send_slack_message(f"Customer upload processed: {parse_result['row_count']} records")

    # Wire up the DAG
    file_info = validate_input()
    parsed = download_and_parse(file_info)
    schema_ok = validate_schema(file_info, parsed)
    load_to_warehouse(file_info, parsed, schema_ok)
    send_success_notification(file_info, parsed)
```

### Part B: External Webhook Handler

This runs as a separate service (FastAPI, Lambda, Cloud Function, etc.) that receives S3 event notifications and calls Airflow:

```python
# webhook_service/s3_event_handler.py
"""
Standalone webhook handler service.
Deploy as: AWS Lambda, Google Cloud Function, FastAPI endpoint, etc.

Receives S3 event notifications and triggers Airflow DAG runs.
"""
import os
import json
import requests
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

AIRFLOW_API_URL = os.environ["AIRFLOW_API_URL"]  # e.g., https://airflow.company.internal
AIRFLOW_DAG_ID = "process_customer_upload"

# Token management
_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None


def get_airflow_token() -> str:
    """Get a valid JWT token, refreshing if necessary."""
    global _cached_token, _token_expiry

    now = datetime.now(timezone.utc)
    if _cached_token and _token_expiry and now < _token_expiry:
        return _cached_token

    response = requests.post(
        f"{AIRFLOW_API_URL}/auth/token",
        json={
            "username": os.environ["AIRFLOW_USER"],
            "password": os.environ["AIRFLOW_PASSWORD"],
        },
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    _cached_token = data["access_token"]
    # Token expires in ~15 min, refresh after 12 min
    from datetime import timedelta
    _token_expiry = now + timedelta(minutes=12)

    return _cached_token


def trigger_airflow_dag(bucket: str, key: str, file_type: str, source: str) -> str:
    """Trigger the Airflow DAG with the S3 event payload."""
    token = get_airflow_token()

    payload = {
        "conf": {
            "bucket": bucket,
            "key": key,
            "file_type": file_type,
            "source_system": source,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
    }

    response = requests.post(
        f"{AIRFLOW_API_URL}/api/v2/dags/{AIRFLOW_DAG_ID}/dagRuns",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if response.status_code == 200:
        run_id = response.json()["run_id"]
        logger.info(f"Triggered DAG run: {run_id} for s3://{bucket}/{key}")
        return run_id
    else:
        logger.error(f"Failed to trigger DAG: {response.status_code} {response.text}")
        raise RuntimeError(f"Airflow API error: {response.status_code}")


def handle_s3_notification(event: dict, context=None) -> dict:
    """
    AWS Lambda handler for S3 event notifications.

    S3 Bucket → Event Notification → SNS → Lambda → Airflow
    """
    results = []

    for record in event.get("Records", []):
        event_name = record.get("eventName", "")

        # Only handle ObjectCreated events
        if not event_name.startswith("ObjectCreated"):
            logger.info(f"Skipping event type: {event_name}")
            continue

        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        size = record["s3"]["object"].get("size", 0)

        # Determine file type from extension
        if key.endswith(".csv"):
            file_type = "csv"
        elif key.endswith(".parquet"):
            file_type = "parquet"
        elif key.endswith(".json"):
            file_type = "json"
        else:
            logger.info(f"Unknown file type for key: {key}, skipping")
            continue

        # Only process files in the uploads/ prefix
        if not key.startswith("uploads/customers/"):
            logger.info(f"Key {key} not in target prefix, skipping")
            continue

        logger.info(f"Processing S3 event: s3://{bucket}/{key} ({size} bytes)")

        try:
            run_id = trigger_airflow_dag(
                bucket=bucket,
                key=key,
                file_type=file_type,
                source="s3_event_notification",
            )
            results.append({"key": key, "status": "triggered", "run_id": run_id})
        except Exception as e:
            logger.error(f"Failed to trigger for {key}: {e}")
            results.append({"key": key, "status": "failed", "error": str(e)})

    return {"processed": len(results), "results": results}
```

---

## Example 2: Asset-Driven Event Pipeline

A multi-stage pipeline where each stage emits an asset that triggers the next stage. No fixed schedules anywhere — everything is data-driven.

```python
# dags/assets_registry.py — central asset registry
from airflow.sdk import Asset

# Stage 1 output: raw ingested data
RAW_TRANSACTIONS = Asset(
    uri="s3://data-lake/transactions/raw/daily.parquet",
    name="raw_transactions",
    group="payments",
    extra={"stage": 1, "description": "Raw transaction records from payment processor"},
)

# Stage 2 output: cleaned and validated
CLEAN_TRANSACTIONS = Asset(
    uri="s3://data-lake/transactions/clean/daily.parquet",
    name="clean_transactions",
    group="payments",
    extra={"stage": 2, "description": "Deduplicated, validated transactions"},
)

# Stage 3 output: aggregated metrics
DAILY_METRICS = Asset(
    uri="s3://data-lake/metrics/daily.parquet",
    name="daily_payment_metrics",
    group="payments",
    extra={"stage": 3, "description": "Daily aggregated payment metrics"},
)

# Final output: dashboard-ready data
DASHBOARD_SNAPSHOT = Asset(
    uri="s3://data-warehouse/dashboards/payments_snapshot.parquet",
    name="payments_dashboard_snapshot",
    group="dashboards",
)
```

```python
# dags/stage1_ingest.py — triggered by external system or cron
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
from assets_registry import RAW_TRANSACTIONS

with DAG(
    dag_id="ingest_transactions",
    start_date=datetime(2024, 1, 1),
    schedule=None,       # Triggered by payment processor webhook
    catchup=False,
    tags=["stage-1", "ingestion"],
) as dag:

    @task
    def authenticate_source(**context) -> dict:
        conf = context["dag_run"].conf or {}
        return {
            "api_endpoint": conf.get("source_api", "https://payments.internal/api"),
            "date": conf.get("date", context["logical_date"].date().isoformat()),
        }

    @task(outlets=[RAW_TRANSACTIONS])    # Emits event when complete
    def fetch_and_store(source_info: dict) -> dict:
        """Pull transactions from payment processor and store raw."""
        print(f"Fetching transactions for {source_info['date']}")
        print(f"Storing to: s3://data-lake/transactions/raw/daily.parquet")

        # Simulated fetch + store
        return {
            "records_fetched": 28450,
            "date": source_info["date"],
            "output_path": "s3://data-lake/transactions/raw/daily.parquet",
        }

    @task
    def log_ingestion_stats(stats: dict):
        print(f"Ingestion complete: {stats['records_fetched']} records for {stats['date']}")

    source = authenticate_source()
    stats = fetch_and_store(source)
    log_ingestion_stats(stats)
```

```python
# dags/stage2_clean.py — triggered by raw_transactions asset
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
from assets_registry import RAW_TRANSACTIONS, CLEAN_TRANSACTIONS

with DAG(
    dag_id="clean_transactions",
    start_date=datetime(2024, 1, 1),
    schedule=[RAW_TRANSACTIONS],    # Runs when stage 1 produces data
    catchup=False,
    tags=["stage-2", "cleaning"],
) as dag:

    @task
    def log_trigger(**context) -> dict:
        """Log what triggered this run."""
        events = context.get("triggering_asset_events", {})
        for uri, event_list in events.items():
            for event in event_list:
                print(f"Triggered by asset: {uri}")
                print(f"Produced by: {event.source_dag_id} run {event.source_run_id}")
                print(f"Asset updated at: {event.timestamp}")
        return {"input_path": "s3://data-lake/transactions/raw/daily.parquet"}

    @task
    def deduplicate(paths: dict) -> int:
        """Remove duplicate transactions."""
        print(f"Reading raw data from {paths['input_path']}")
        # df = pd.read_parquet(paths["input_path"])
        # df_dedup = df.drop_duplicates(subset=["transaction_id"])
        raw_count = 28450
        dedup_count = 27800  # simulated
        print(f"Removed {raw_count - dedup_count} duplicates")
        return dedup_count

    @task
    def validate_amounts(record_count: int) -> int:
        """Validate transaction amounts are within expected range."""
        # Simulate validation — flag negative amounts, extreme outliers
        invalid_count = 12
        valid_count = record_count - invalid_count
        print(f"Validated amounts: {valid_count} valid, {invalid_count} flagged")
        return valid_count

    @task(outlets=[CLEAN_TRANSACTIONS])    # Emits event when complete
    def write_clean_data(valid_count: int) -> dict:
        """Write cleaned data and emit the clean_transactions asset event."""
        output = "s3://data-lake/transactions/clean/daily.parquet"
        print(f"Writing {valid_count} clean records to {output}")
        return {"output_path": output, "record_count": valid_count}

    paths = log_trigger()
    dedup_count = deduplicate(paths)
    valid_count = validate_amounts(dedup_count)
    write_clean_data(valid_count)
```

```python
# dags/stage3_aggregate.py — triggered by clean_transactions asset
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
from assets_registry import CLEAN_TRANSACTIONS, DAILY_METRICS

with DAG(
    dag_id="aggregate_metrics",
    start_date=datetime(2024, 1, 1),
    schedule=[CLEAN_TRANSACTIONS],
    catchup=False,
    tags=["stage-3", "aggregation"],
) as dag:

    @task(outlets=[DAILY_METRICS])
    def compute_and_store_metrics(**context) -> dict:
        """Aggregate clean transactions into daily metrics."""
        events = context.get("triggering_asset_events", {})
        print(f"Computing metrics. Triggered by: {list(events.keys())}")

        # df = pd.read_parquet("s3://data-lake/transactions/clean/daily.parquet")
        metrics = {
            "total_volume": 2_840_500.00,
            "transaction_count": 27788,
            "avg_transaction": 102.22,
            "success_rate": 0.9981,
        }

        print(f"Metrics computed: {metrics}")
        return metrics

    compute_and_store_metrics()
```

```python
# dags/stage4_dashboard.py — final consumer, updates dashboard
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
from assets_registry import DAILY_METRICS, DASHBOARD_SNAPSHOT

with DAG(
    dag_id="refresh_dashboard",
    start_date=datetime(2024, 1, 1),
    schedule=[DAILY_METRICS],
    catchup=False,
    tags=["stage-4", "dashboard"],
) as dag:

    @task(outlets=[DASHBOARD_SNAPSHOT])
    def build_dashboard_snapshot(**context) -> dict:
        """Create dashboard-ready snapshot from metrics."""
        events = context.get("triggering_asset_events", {})
        print(f"Building dashboard snapshot. Triggered by: {list(events.keys())}")

        # df_metrics = pd.read_parquet("s3://data-lake/metrics/daily.parquet")
        # Build enriched snapshot with rolling averages, period-over-period, etc.
        print("Dashboard snapshot written to warehouse")
        return {"status": "refreshed"}

    @task
    def invalidate_cache(result: dict):
        """Tell the BI tool to refresh its cache."""
        print(f"Sending cache invalidation signal to BI platform")
        # requests.post("https://bi-platform.internal/api/refresh", ...)

    snapshot = build_dashboard_snapshot()
    invalidate_cache(snapshot)
```

### The Full Chain (No Fixed Schedules)

```
Payment processor webhook
         │
         ▼
   ingest_transactions  →  RAW_TRANSACTIONS asset
                                     │
                                     ▼
                           clean_transactions  →  CLEAN_TRANSACTIONS asset
                                                           │
                                                           ▼
                                                 aggregate_metrics  →  DAILY_METRICS asset
                                                                                │
                                                                                ▼
                                                                      refresh_dashboard  →  DASHBOARD_SNAPSHOT asset
```

Each stage runs immediately when its upstream data is ready. The entire chain from payment processor webhook to refreshed dashboard completes as fast as the processing allows — not on a fixed schedule.

---

## Navigation
⬅️ **Prev: [Edge Executor](../34_Edge_Executor/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Object Storage](../36_Object_Storage/Theory.md)**
