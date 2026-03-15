# 28 — Remote Logging: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Remote Logging Backend Config Table

| Backend | Provider Package | `remote_log_conn_id` Conn Type | `remote_base_log_folder` Format |
|---|---|---|---|
| Amazon S3 | `apache-airflow-providers-amazon` | `Amazon Web Services` | `s3://bucket/prefix` |
| Google Cloud Storage | `apache-airflow-providers-google` | `Google Cloud` | `gs://bucket/prefix` |
| Azure Blob Storage | `apache-airflow-providers-microsoft-azure` | `Azure Blob Storage` | `wasb-container/prefix` |
| Elasticsearch | `apache-airflow-providers-elasticsearch` | N/A (separate config section) | Index name in `[elasticsearch]` |
| Local Filesystem | Built-in | N/A | `file:///path/to/logs` |

---

## airflow.cfg [logging] Section

```ini
[logging]
# Enable remote logging
remote_logging = True

# Airflow connection ID that has access to the remote log store
remote_log_conn_id = aws_default

# Root path in the remote store
remote_base_log_folder = s3://my-airflow-logs/logs

# Only for S3: encrypt logs at rest with SSE
encrypt_s3_logs = False

# Log level for task logs
logging_level = INFO

# Log level for DAG processing (separate from task logs)
dag_processor_manager_log_location = /opt/airflow/logs/dag_processor_manager/dag_processor_manager.log
```

---

## Per-Backend Configuration

### S3
```ini
[logging]
remote_logging = True
remote_log_conn_id = aws_default
remote_base_log_folder = s3://my-airflow-logs/airflow-task-logs
encrypt_s3_logs = False
```

### GCS
```ini
[logging]
remote_logging = True
remote_log_conn_id = google_cloud_default
remote_base_log_folder = gs://my-airflow-logs/airflow-task-logs
```

### Azure Blob
```ini
[logging]
remote_logging = True
remote_log_conn_id = wasb_default
remote_base_log_folder = wasb-airflow-logs/airflow-task-logs
```

### Elasticsearch
```ini
[logging]
remote_logging = True

[elasticsearch]
host = http://elasticsearch:9200
log_id_template = {dag_id}-{task_id}-{run_id}-{map_index}-{try_number}
end_of_log_mark = end_of_log
write_stdout = False
json_format = True
json_fields = asctime,filename,lineno,levelname,message
```

---

## Required Connections

### aws_default (S3)
```
Conn Type:  Amazon Web Services
Extra:      {"region_name": "us-east-1"}
Login:      <access_key_id>        (if not using IAM role)
Password:   <secret_access_key>    (if not using IAM role)
```

### google_cloud_default (GCS)
```
Conn Type:   Google Cloud
Key File:    /opt/airflow/gsa-key.json
  OR
Keyfile JSON: {"type": "service_account", ...}
```

### wasb_default (Azure Blob)
```
Conn Type:    Azure Blob Storage
Account Name: mystorageaccount
Account Key:  <storage_account_key>
```

---

## Log Folder Structure in S3/GCS

```
<remote_base_log_folder>/
└── dag_id=<dag_id>/
    └── run_id=<run_id>/
        └── task_id=<task_id>/
            ├── attempt=1.log
            ├── attempt=2.log    (if task was retried)
            └── attempt=3.log
```

Example:
```
s3://my-airflow-logs/logs/
└── dag_id=orders_daily/
    └── run_id=scheduled__2026-03-15T00:00:00+00:00/
        └── task_id=extract_orders/
            └── attempt=1.log
```

---

## Retention Cleanup

### S3 Lifecycle Policy (JSON for console or CLI)
```json
{
    "Rules": [{
        "Id": "airflow-log-expiry-90-days",
        "Status": "Enabled",
        "Filter": {"Prefix": "airflow-task-logs/"},
        "Expiration": {"Days": 90}
    }]
}
```

Apply:
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket my-airflow-logs \
  --lifecycle-configuration file://lifecycle.json
```

### Local Log Cleanup Command
```bash
# Delete task logs older than 7 days
find $AIRFLOW_HOME/logs -type f -name "*.log" -mtime +7 -delete

# Delete empty directories left behind
find $AIRFLOW_HOME/logs -mindepth 1 -type d -empty -delete
```

### Database Log Cleanup (metadata DB records, not files)
```bash
airflow db clean \
  --clean-before-timestamp "2026-01-01T00:00:00" \
  --tables log \
  --yes
```

---

## Environment Variables (Docker/Kubernetes)

```bash
export AIRFLOW__LOGGING__REMOTE_LOGGING=True
export AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=aws_default
export AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=s3://my-bucket/logs
export AIRFLOW__LOGGING__LOGGING_LEVEL=INFO
```

## Kubernetes Pod Annotation for Log Collection (sidecar pattern)

When not using Airflow remote logging, you can collect logs via a Fluent Bit sidecar:
```yaml
# KubernetesExecutor pod_override
annotations:
  fluentbit.io/parser: "airflow"
  fluentbit.io/exclude: "false"
```
