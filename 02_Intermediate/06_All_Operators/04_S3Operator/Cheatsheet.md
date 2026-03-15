# S3 Operators — Cheatsheet

Quick reference for working with AWS S3 from Airflow. Covers the full operator catalogue, key parameters, common patterns, and authentication options.

---

## What They Do in One Sentence

S3 operators move files between local storage and AWS S3 (or between S3 buckets), manage bucket lifecycle, and integrate cloud storage into your DAG with built-in AWS authentication.

---

## Provider Package

```bash
pip install apache-airflow-providers-amazon
```

Not part of Airflow core. Covers S3, Redshift, EMR, Glue, Lambda, and many other AWS services.

---

## Imports

```python
# Operators
from airflow.providers.amazon.aws.operators.s3 import (
    S3CreateBucketOperator,
    S3DeleteBucketOperator,
    S3CopyObjectOperator,
    S3DeleteObjectsOperator,
    S3FileTransformOperator,
)

# Transfers
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator
from airflow.providers.amazon.aws.transfers.s3_to_local import S3ToLocalFilesystemOperator

# Sensor
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
```

---

## Operator Quick Reference

| Operator | What it does | Key params |
|---|---|---|
| `LocalFilesystemToS3Operator` | Local file → S3 | `filename`, `dest_key`, `dest_bucket` |
| `S3ToLocalFilesystemOperator` | S3 → local file | `s3_key`, `bucket_name`, `local_path` |
| `S3CreateBucketOperator` | Create bucket (idempotent) | `bucket_name`, `region_name` |
| `S3DeleteBucketOperator` | Delete bucket | `bucket_name`, `force_delete` |
| `S3CopyObjectOperator` | Copy object (server-side) | `source_bucket_name`, `source_bucket_key`, `dest_bucket_name`, `dest_bucket_key` |
| `S3DeleteObjectsOperator` | Delete objects | `bucket`, `keys` or `prefix` |
| `S3FileTransformOperator` | Download → transform script → upload | `source_s3_key`, `dest_s3_key`, `transform_script` |
| `S3KeySensor` | Wait until a key exists | `bucket_name`, `bucket_key`, `poke_interval`, `timeout` |

---

## Key Parameters (Shared)

| Parameter | Description |
|---|---|
| `aws_conn_id` | Airflow connection ID for AWS auth (default: `"aws_default"`) |
| `bucket_name` | Name of the S3 bucket |
| `source_bucket_key` | S3 key (path) of the source object |
| `dest_bucket_key` | S3 key (path) of the destination object |
| `region_name` | AWS region (e.g., `"us-east-1"`) — override per operator if needed |

---

## Template Fields (Jinja-aware)

`filename`, `dest_key`, `source_bucket_key`, `dest_bucket_key`, `bucket_key`, `keys` — all support `{{ ds }}`, `{{ run_id }}`, `{{ ds_nodash }}`, etc.

---

## Code Patterns

### Upload Local File to S3

```python
LocalFilesystemToS3Operator(
    task_id="upload_report",
    filename="/tmp/report_{{ ds }}.csv",
    dest_key="reports/daily/{{ ds }}/report.csv",
    dest_bucket="my-data-bucket",
    aws_conn_id="aws_default",
    replace=True,
)
```

---

### Copy Between Buckets (Server-Side)

```python
S3CopyObjectOperator(
    task_id="archive",
    source_bucket_name="my-staging-bucket",
    source_bucket_key="staging/{{ ds }}/data.csv",
    dest_bucket_name="my-archive-bucket",
    dest_bucket_key="archive/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
)
```

No data flows through the Airflow worker — S3 copies server-side. Fast and bandwidth-free.

---

### Delete Objects After Processing

```python
S3DeleteObjectsOperator(
    task_id="cleanup_staging",
    bucket="my-staging-bucket",
    keys=["staging/{{ ds }}/data.csv", "staging/{{ ds }}/meta.json"],
    aws_conn_id="aws_default",
)

# Or delete by prefix (all objects under a path)
S3DeleteObjectsOperator(
    task_id="cleanup_prefix",
    bucket="my-staging-bucket",
    prefix="staging/{{ ds }}/",
    aws_conn_id="aws_default",
)
```

---

### Transform a File In-Flight

```python
S3FileTransformOperator(
    task_id="transform",
    source_s3_key="s3://my-bucket/raw/{{ ds }}/data.csv",
    dest_s3_key="s3://my-bucket/clean/{{ ds }}/data.csv",
    transform_script="/opt/airflow/scripts/clean.py",
    aws_conn_id="aws_default",
)
```

The transform script receives local source path as `sys.argv[1]` and destination path as `sys.argv[2]`.

---

### Wait for a File to Appear (Sensor)

```python
S3KeySensor(
    task_id="wait_for_upstream",
    bucket_name="my-input-bucket",
    bucket_key="incoming/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
    poke_interval=60,      # seconds between checks
    timeout=3600,          # give up after 1 hour
    mode="reschedule",     # free the worker slot between checks
)
```

---

### Ensure Bucket Exists (Pipeline Setup)

```python
S3CreateBucketOperator(
    task_id="ensure_bucket",
    bucket_name="my-pipeline-output",
    region_name="us-east-1",
    aws_conn_id="aws_default",
)
```

---

### Full Pipeline Pattern

```python
ensure_bucket >> generate_data >> upload_to_s3 >> copy_to_archive >> delete_staging
```

---

## Authentication Options

| Method | Setup | Best for |
|---|---|---|
| Access key + secret | Store in Airflow connection (login/password fields) | Local dev, third-party hosted |
| IAM role (instance profile) | Leave connection credentials blank; EC2/ECS role auto-used | Production on AWS EC2/ECS |
| IAM role (IRSA / EKS) | Add `role_arn` to connection Extra JSON | Kubernetes on EKS |
| Cross-account role | Add `role_arn` of target account to connection Extra JSON | Multi-account setups |

Connection Extra JSON for role assumption:
```json
{
    "region_name": "us-east-1",
    "role_arn": "arn:aws:iam::123456789:role/AirflowRole",
    "role_session_name": "airflow"
}
```

---

## When to Use S3 Operators

| Use them when... | Avoid them when... |
|---|---|
| Uploading pipeline outputs to S3 | Very large files requiring streaming (use custom boto3 code) |
| Archiving/moving files between buckets | Real-time streaming data (use Kinesis, Kafka) |
| Waiting for upstream files to land in S3 | Heavy transforms (use AWS Glue, EMR, or Spark operators) |
| Data lake ELT workflows | You need fine-grained error handling per object |
| Cleaning up staging areas after processing | Complex multi-file coordination (consider Step Functions) |

---

## Common Pitfalls

1. **Missing IAM permissions** — the most common failure; ensure `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` are granted on both bucket ARN and `bucket-name/*`
2. **Region mismatch** — bucket and connection must agree on region; otherwise you get 301 redirects or endpoint errors
3. **No `replace=True` on uploads** — without it, `LocalFilesystemToS3Operator` fails if the key already exists
4. **Sensor blocks a worker slot** — always use `mode="reschedule"` on `S3KeySensor` so it frees the worker between checks
5. **`S3FileTransformOperator` loads to disk** — for large files, disk space on the worker can be exhausted; monitor worker storage

---

## Golden Rules

- Use IAM roles, not access keys, in production — credentials are auto-rotated and never stored as plaintext
- Always set `replace=True` on uploads for idempotent pipelines — re-runs should overwrite, not fail
- Use `S3CopyObjectOperator` for bucket-to-bucket moves — it is server-side and never touches the worker
- Use `mode="reschedule"` on `S3KeySensor` to avoid locking up a worker while waiting
- Keep S3 keys predictable and date-based (`prefix/{{ ds }}/filename`) — makes cleanup, partitioning, and debugging much easier

---

## IAM Permissions Quick Reference

```json
{
  "Action": [
    "s3:GetObject",       "s3:PutObject",
    "s3:DeleteObject",    "s3:ListBucket",
    "s3:CreateBucket",    "s3:GetObjectAcl",
    "s3:PutObjectAcl"
  ],
  "Resource": [
    "arn:aws:s3:::your-bucket",
    "arn:aws:s3:::your-bucket/*"
  ]
}
```

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview prep |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [03_PostgresOperator](../03_PostgresOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [05_HttpOperator](../05_HttpOperator/Theory.md)
