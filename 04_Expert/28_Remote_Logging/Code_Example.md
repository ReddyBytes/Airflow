# Remote Logging — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Patterns & Best Practices](../29_DAG_Patterns_Best_Practices/Theory.md)**

---

## Example 1: S3 Remote Logging — Environment Variables

The most portable configuration. Set these on every container that runs tasks (workers, scheduler for LocalExecutor).

```bash
# Minimum required for S3 remote logging
export AIRFLOW__LOGGING__REMOTE_LOGGING=True
export AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=s3://my-airflow-logs/
export AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=aws_default

# Optional: control local log buffer before upload
export AIRFLOW__LOGGING__BASE_LOG_FOLDER=/opt/airflow/logs
export AIRFLOW__LOGGING__LOG_FILENAME_TEMPLATE="{{ ti.dag_id }}/{{ ti.run_id }}/{{ ti.task_id }}/{{ ti.try_number }}.log"
```

The Airflow connection `aws_default` must exist:
```bash
# Create the S3 connection via CLI
airflow connections add aws_default \
  --conn-type aws \
  --conn-extra '{"region_name": "us-east-1"}'

# For key-based auth (not recommended for production):
airflow connections add aws_default \
  --conn-type aws \
  --conn-login YOUR_ACCESS_KEY_ID \
  --conn-password YOUR_SECRET_ACCESS_KEY \
  --conn-extra '{"region_name": "us-east-1"}'
```

---

## Example 2: S3 Remote Logging — Docker Compose

A complete Docker Compose configuration with S3 remote logging enabled for all components.

```yaml
# docker-compose.yml
version: "3.8"

x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    &airflow-common-env
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__EXECUTOR: CeleryExecutor
    AIRFLOW__CELERY__BROKER_URL: redis://redis:6379/0
    AIRFLOW__CELERY__RESULT_BACKEND: db+postgresql://airflow:airflow@postgres/airflow

    # ── Remote logging ───────────────────────────────────────────────────────
    AIRFLOW__LOGGING__REMOTE_LOGGING: "True"
    AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER: "s3://my-airflow-logs/logs/"
    AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID: "aws_default"
    AIRFLOW__LOGGING__ENCRYPT_S3_LOGS: "False"  # set True for KMS encryption

    # AWS credentials via environment (or use IAM role attachment for production)
    AWS_DEFAULT_REGION: "us-east-1"
    # AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY via .env or secrets manager

  volumes:
    - ./dags:/opt/airflow/dags
    - ./plugins:/opt/airflow/plugins
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s

  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  airflow-init:
    <<: *airflow-common
    command: >
      bash -c "
        airflow db migrate &&
        airflow users create --username admin --password admin
          --firstname Admin --lastname User --role Admin --email admin@example.com &&
        airflow connections add aws_default --conn-type aws
          --conn-extra '{\"region_name\": \"us-east-1\"}'
      "

  api-server:
    <<: *airflow-common
    command: api-server
    ports:
      - "8080:8080"

  dag-processor:
    <<: *airflow-common
    command: dag-processor

  scheduler:
    <<: *airflow-common
    command: scheduler

  worker:
    <<: *airflow-common
    command: celery worker
    # Worker MUST have remote logging config — it is the one that writes logs
```

---

## Example 3: GCS Remote Logging Configuration

```yaml
# docker-compose — GCS remote logging
environment:
  AIRFLOW__LOGGING__REMOTE_LOGGING: "True"
  AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER: "gs://my-airflow-logs/logs/"
  AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID: "google_cloud_default"
```

Create the GCS connection:
```bash
# Via CLI — point to a service account key file
airflow connections add google_cloud_default \
  --conn-type google_cloud_platform \
  --conn-extra '{"key_path": "/run/secrets/sa-key.json", "scope": "https://www.googleapis.com/auth/cloud-platform"}'

# Or via Workload Identity (GKE) — no credentials needed, leave connection empty
airflow connections add google_cloud_default \
  --conn-type google_cloud_platform \
  --conn-extra '{}'
```

Verify bucket access before enabling:
```bash
python -c "
from airflow.providers.google.cloud.hooks.gcs import GCSHook
hook = GCSHook(gcp_conn_id='google_cloud_default')
hook.create_bucket('my-airflow-logs', location='US')
print('Bucket access OK')
"
```

---

## Example 4: Elasticsearch Remote Logging Configuration

Elasticsearch is the right choice when you need to search log content across tasks, or integrate with an existing ELK/OpenSearch stack.

```ini
# airflow.cfg — Elasticsearch logging
[logging]
remote_logging = True

# Use ElasticsearchTaskHandler instead of S3/GCS handler
logging_config_class = airflow.providers.elasticsearch.log.es_task_handler.ElasticsearchTaskHandler

[elasticsearch]
host = https://my-elasticsearch.example.com:9200
# For basic auth:
# user = elastic
# pass = mypassword
# For API key auth:
# api_key = base64encodedapikey

# Unique log identifier per task attempt
log_id_template = {dag_id}-{task_id}-{run_id}-{map_index}-{try_number}

# Marker written at the end of each log stream
end_of_log_mark = end_of_log

# Write to stdout as well (useful when logs are also captured by a log aggregator)
write_stdout = False

# Emit log records as JSON for structured logging
json_format = True
json_fields = asctime,filename,lineno,levelname,message
```

Environment variable form:
```bash
export AIRFLOW__LOGGING__REMOTE_LOGGING=True
export AIRFLOW__ELASTICSEARCH__HOST=https://my-es.example.com:9200
export AIRFLOW__ELASTICSEARCH__LOG_ID_TEMPLATE="{dag_id}-{task_id}-{run_id}-{try_number}"
export AIRFLOW__ELASTICSEARCH__JSON_FORMAT=True
```

Install the provider:
```bash
pip install apache-airflow-providers-elasticsearch
```

Test connectivity:
```bash
python -c "
from elasticsearch import Elasticsearch
es = Elasticsearch('https://my-es.example.com:9200')
print(es.info())
"
```

---

## Example 5: Testing That Log Upload Works

Use this script to verify the full remote logging pipeline before deploying to production.

```python
#!/usr/bin/env python
# scripts/verify_remote_logging.py
"""
End-to-end test for remote logging configuration.
Run this before deploying to production.

Usage:
    python verify_remote_logging.py --backend s3
    python verify_remote_logging.py --backend gcs
"""
import argparse
import os
import sys
from datetime import datetime


def test_s3_logging():
    """Verify S3 logging connection and write permissions."""
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    conn_id = os.environ.get("AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID", "aws_default")
    log_folder = os.environ.get("AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER", "")

    if not log_folder.startswith("s3://"):
        print("ERROR: AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER must start with s3://")
        sys.exit(1)

    # Parse bucket and prefix
    parts = log_folder[5:].split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""

    print(f"Testing S3 connection: conn_id={conn_id}, bucket={bucket}")

    try:
        hook = S3Hook(aws_conn_id=conn_id)

        # Test read access
        if not hook.check_for_bucket(bucket):
            print(f"ERROR: Bucket '{bucket}' not found or no access")
            sys.exit(1)
        print(f"  Bucket '{bucket}': accessible")

        # Test write access
        test_key = f"{prefix}airflow-logging-test/{datetime.utcnow().isoformat()}.txt"
        hook.load_string("logging test", key=test_key, bucket_name=bucket)
        print(f"  Write test: OK ({test_key})")

        # Test read access
        content = hook.read_key(key=test_key, bucket_name=bucket)
        assert content == "logging test", "Read back unexpected content"
        print(f"  Read test: OK")

        # Clean up test file
        hook.delete_objects(bucket=bucket, keys=[test_key])
        print(f"  Cleanup: OK")

        print("\nS3 remote logging configuration: VALID")

    except Exception as e:
        print(f"\nERROR: S3 test failed: {e}")
        sys.exit(1)


def test_gcs_logging():
    """Verify GCS logging connection and write permissions."""
    from airflow.providers.google.cloud.hooks.gcs import GCSHook

    conn_id = os.environ.get("AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID", "google_cloud_default")
    log_folder = os.environ.get("AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER", "")

    if not log_folder.startswith("gs://"):
        print("ERROR: AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER must start with gs://")
        sys.exit(1)

    parts = log_folder[5:].split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""

    print(f"Testing GCS connection: conn_id={conn_id}, bucket={bucket}")

    try:
        hook = GCSHook(gcp_conn_id=conn_id)

        # Test write
        test_object = f"{prefix}airflow-logging-test/{datetime.utcnow().isoformat()}.txt"
        hook.upload(
            bucket_name=bucket,
            object_name=test_object,
            data="logging test",
            mime_type="text/plain",
        )
        print(f"  Write test: OK ({test_object})")

        # Test read
        content = hook.download(bucket_name=bucket, object_name=test_object)
        assert content.decode() == "logging test"
        print(f"  Read test: OK")

        # Cleanup
        hook.delete(bucket_name=bucket, object_name=test_object)
        print(f"  Cleanup: OK")

        print("\nGCS remote logging configuration: VALID")

    except Exception as e:
        print(f"\nERROR: GCS test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["s3", "gcs"], required=True)
    args = parser.parse_args()

    if args.backend == "s3":
        test_s3_logging()
    elif args.backend == "gcs":
        test_gcs_logging()
```

Run it:
```bash
# Test S3 config before deploying
AIRFLOW__LOGGING__REMOTE_LOGGING=True \
AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=s3://my-airflow-logs/ \
AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=aws_default \
python scripts/verify_remote_logging.py --backend s3
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Patterns & Best Practices](../29_DAG_Patterns_Best_Practices/Theory.md)**
