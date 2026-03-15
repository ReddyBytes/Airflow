# 28 — Remote Logging

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## The Story

Your Airflow tasks are running on Kubernetes pods that disappear after execution. The pod that ran your task 5 hours ago is gone. So are the logs — unless you configured remote logging. With remote logging, every task log line is streamed to S3, GCS, or Azure Blob in real time. The Airflow UI reads from the remote store transparently. Logs persist indefinitely, are searchable, and are accessible even after workers restart, scale down, or crash.

---

## 1. Local Logging (Default)

By default, Airflow writes task logs to `$AIRFLOW_HOME/logs/`:

```
$AIRFLOW_HOME/logs/
├── scheduler/
│   └── 2026-03-15/
│       └── my_dag.py.log
└── dag_id=my_dag/
    └── run_id=scheduled__2026-03-15/
        └── task_id=my_task/
            └── attempt=1.log
```

Problems with local logging:
- Logs lost when workers restart or pods terminate
- No centralized access — need to SSH into each worker
- No retention policy (disk fills up)
- Doesn't scale with ephemeral workers

---

## 2. Remote Logging Configuration

All remote logging backends are configured in `airflow.cfg` under `[logging]`:

```ini
[logging]
remote_logging = True
remote_log_conn_id = <airflow_conn_id>
remote_base_log_folder = <bucket_or_container_path>
encrypt_s3_logs = False       # S3 only
logging_level = INFO
```

Airflow writes logs to both local disk and remote simultaneously during task execution. When viewing logs in the UI, Airflow first checks if a remote log exists and reads from there if so.

---

## 3. S3 Logging

### Connection Setup
```
Conn ID:    aws_s3_logs
Conn Type:  Amazon Web Services
Extra:      {"region_name": "us-east-1"}
```

Or via IAM instance profile / EKS IRSA — no connection needed if the Airflow process has S3 access.

### airflow.cfg
```ini
[logging]
remote_logging = True
remote_log_conn_id = aws_default
remote_base_log_folder = s3://my-company-airflow-logs/airflow-logs
encrypt_s3_logs = False
logging_level = INFO
```

### Environment Variable Configuration
```bash
export AIRFLOW__LOGGING__REMOTE_LOGGING=True
export AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=aws_default
export AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=s3://my-company-airflow-logs/airflow-logs
```

### Log Path Structure in S3
```
s3://my-company-airflow-logs/airflow-logs/
└── dag_id=my_dag/
    └── run_id=scheduled__2026-03-15T00:00:00+00:00/
        └── task_id=my_task/
            └── attempt=1.log
```

### Required IAM Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket"
        ],
        "Resource": [
            "arn:aws:s3:::my-company-airflow-logs",
            "arn:aws:s3:::my-company-airflow-logs/*"
        ]
    }]
}
```

---

## 4. GCS Logging

### airflow.cfg
```ini
[logging]
remote_logging = True
remote_log_conn_id = google_cloud_default
remote_base_log_folder = gs://my-company-airflow-logs/airflow-logs
logging_level = INFO
```

### Connection
```
Conn ID:    google_cloud_default
Conn Type:  Google Cloud
Key File:   /path/to/service-account.json
  OR
Scopes:     https://www.googleapis.com/auth/devstorage.read_write
```

### Required Service Account Permissions
- `roles/storage.objectAdmin` on the GCS bucket, or custom role with:
  - `storage.objects.create`
  - `storage.objects.get`
  - `storage.objects.delete`
  - `storage.buckets.get`

---

## 5. Azure Blob Storage Logging

### Installation
```bash
pip install apache-airflow-providers-microsoft-azure
```

### airflow.cfg
```ini
[logging]
remote_logging = True
remote_log_conn_id = wasb_default
remote_base_log_folder = wasb-airflow-logs/airflow-logs
logging_level = INFO
```

### Connection
```
Conn ID:    wasb_default
Conn Type:  Azure Blob Storage
Account Name:   mycompanystorageaccount
Account Key:    <storage_account_key>
  OR
SAS Token:  <sas_token>
```

---

## 6. Elasticsearch Logging

Elasticsearch logging stores logs in an index, enabling full-text search across all task logs.

### Installation
```bash
pip install apache-airflow-providers-elasticsearch
```

### airflow.cfg
```ini
[logging]
remote_logging = True

[elasticsearch]
host = http://elasticsearch.corp.com:9200
log_id_template = {dag_id}-{task_id}-{run_id}-{map_index}-{try_number}
end_of_log_mark = end_of_log
write_stdout = False
json_format = False
json_fields = asctime,filename,lineno,levelname,message
frontend = http://kibana.corp.com:5601/app/discover#/?_g=(time:(from:now-1d,to:now))&_a=(query:(language:kuery,query:'{log_id}'))
```

Elasticsearch logging enables the "Kibana link" button in the Airflow task log view.

---

## 7. Log Retention and Cleanup

### S3 Lifecycle Policy
```json
{
    "Rules": [{
        "Id": "AirflowLogRetention",
        "Status": "Enabled",
        "Filter": {"Prefix": "airflow-logs/"},
        "Expiration": {"Days": 90},
        "NoncurrentVersionExpiration": {"NoncurrentDays": 7}
    }]
}
```

### Local Log Cleanup (even with remote logging, clean local logs)
```bash
# Clean local logs older than 7 days
find $AIRFLOW_HOME/logs -type f -name "*.log" -mtime +7 -delete
find $AIRFLOW_HOME/logs -type d -empty -delete
```

Schedule this as a DAG:
```python
# dags/log_cleanup.py
from airflow.sdk import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="log_cleanup",
    schedule="0 1 * * *",   # Daily at 1 AM
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["maintenance"],
) as dag:

    clean_local = BashOperator(
        task_id="clean_local_logs",
        bash_command=(
            "find $AIRFLOW_HOME/logs -type f -name '*.log' -mtime +7 -delete && "
            "find $AIRFLOW_HOME/logs -type d -empty -delete"
        ),
    )
```

---

## 8. Viewing Remote Logs in the UI

When remote logging is configured:
1. The Airflow UI shows an indicator that the log is remote
2. The webserver fetches log content from S3/GCS/Azure via the configured connection
3. If the remote log doesn't exist yet (task still running), it falls back to the local log
4. If both fail, the UI shows "Log file does not exist"

For Kubernetes deployments where there is no local log fallback, ensure workers have write access to the remote store at task startup — the first log line must be written successfully or the UI shows no logs during execution.

---

## Key Takeaways

- Remote logging is essential for ephemeral workers (Kubernetes, ECS) where local disk is not persistent
- Configuration is uniform: `remote_logging = True`, `remote_log_conn_id`, `remote_base_log_folder`
- S3 and GCS are the most common backends; both are well-tested and production-proven
- Set S3 lifecycle policies to automatically expire old logs — do not rely on `airflow db clean` to delete remote logs
- Elasticsearch logging adds full-text search and Kibana integration for debug workflows
- Always clean local logs even when using remote logging — workers have limited disk and tasks write locally first
