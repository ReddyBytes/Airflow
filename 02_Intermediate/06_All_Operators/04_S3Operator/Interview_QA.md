# S3 Operators — Interview Q&A

Cloud storage is central to modern data pipelines. Interviewers will test whether you understand how Airflow authenticates with AWS, which operator does what, and when to reach for something beyond the basic operators.

---

## Beginner Questions

**Q1. What AWS connection does Airflow S3 operators use? How do you configure it?**

All S3 operators use an **Amazon Web Services connection** stored in Airflow's connection store. The default connection ID is `aws_default`.

Setup via the Airflow UI:
1. Install the provider: `pip install apache-airflow-providers-amazon`
2. Go to **Admin → Connections → +**
3. Set Connection Type to `Amazon Web Services`
4. Fill in AWS Access Key ID and AWS Secret Access Key
5. In the Extra field, add region: `{"region_name": "us-east-1"}`

Setup via environment variable:
```bash
export AIRFLOW_CONN_AWS_DEFAULT='{"conn_type": "aws", "login": "AKIAIOSFODNN7", "password": "wJalrXUtnFEMI", "extra": {"region_name": "us-east-1"}}'
```

If Airflow runs on AWS (EC2, ECS, EKS) with an IAM role attached, you can create the connection with no credentials — Airflow will use the instance profile automatically.

---

**Q2. What is `aws_conn_id`?**

`aws_conn_id` is the parameter that tells an S3 operator which Airflow connection to use for AWS authentication. Every S3 operator has it:

```python
S3CreateBucketOperator(
    task_id="create_bucket",
    bucket_name="my-data-bucket",
    aws_conn_id="aws_default",    # references your stored AWS credentials
)
```

The default is `"aws_default"` — if you named your connection that, you can omit the parameter.

---

**Q3. What are the most common S3 operations available as Airflow operators?**

| Operator | What it does |
|---|---|
| `LocalFilesystemToS3Operator` | Upload a local file to S3 |
| `S3ToLocalFilesystemOperator` | Download an S3 object to local disk |
| `S3CreateBucketOperator` | Create an S3 bucket (idempotent) |
| `S3DeleteBucketOperator` | Delete an S3 bucket |
| `S3CopyObjectOperator` | Copy an object within or between buckets |
| `S3DeleteObjectsOperator` | Delete one or more S3 objects |
| `S3FileTransformOperator` | Download, transform with a script, re-upload |
| `S3KeySensor` | Wait (sensor) until an S3 key exists |

---

**Q4. Which package do you need to install for S3 operators?**

```bash
pip install apache-airflow-providers-amazon
```

This is the Amazon provider package — not included in Airflow core. It covers S3, Redshift, EMR, Lambda, Glue, and many other AWS services.

---

**Q5. How do you upload a local file to S3?**

Use `LocalFilesystemToS3Operator`:

```python
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator

upload = LocalFilesystemToS3Operator(
    task_id="upload_report",
    filename="/tmp/report_{{ ds }}.csv",       # local file path (Jinja-enabled)
    dest_key="reports/daily/{{ ds }}/report.csv",  # S3 key (path in bucket)
    dest_bucket="my-data-bucket",
    aws_conn_id="aws_default",
    replace=True,    # overwrite if key already exists
)
```

---

## Intermediate Questions

**Q6. How do you copy an S3 object between buckets?**

Use `S3CopyObjectOperator`:

```python
from airflow.providers.amazon.aws.operators.s3 import S3CopyObjectOperator

copy_to_archive = S3CopyObjectOperator(
    task_id="archive_file",
    source_bucket_name="my-staging-bucket",
    source_bucket_key="staging/{{ ds }}/data.csv",
    dest_bucket_name="my-archive-bucket",
    dest_bucket_key="archive/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
)
```

This uses the S3 server-side copy — the file is never downloaded to the Airflow worker. It is fast and does not consume worker network bandwidth.

---

**Q7. How do you transform a file during transfer between S3 locations?**

Use `S3FileTransformOperator`. It downloads the source file, runs your transformation script against it, and uploads the result to the destination:

```python
from airflow.providers.amazon.aws.operators.s3 import S3FileTransformOperator

transform = S3FileTransformOperator(
    task_id="transform_file",
    source_s3_key="s3://my-bucket/raw/{{ ds }}/data.csv",
    dest_s3_key="s3://my-bucket/processed/{{ ds }}/data.csv",
    transform_script="/opt/airflow/scripts/clean.py",
    aws_conn_id="aws_default",
)
```

The transform script is called with the local paths of the downloaded source and the destination output file as arguments:
```python
# clean.py
import sys
import csv

with open(sys.argv[1]) as infile, open(sys.argv[2], "w") as outfile:
    # transform logic here
```

---

**Q8. How does `S3KeySensor` relate to S3 operators? When do you use it?**

`S3KeySensor` is not an operator — it is a **sensor** that pauses the DAG until a specified S3 key (file) exists. Use it to coordinate pipelines that depend on files arriving in S3 from external processes:

```python
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

wait_for_file = S3KeySensor(
    task_id="wait_for_upstream_file",
    bucket_name="my-input-bucket",
    bucket_key="incoming/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
    poke_interval=60,      # check every 60 seconds
    timeout=3600,          # fail after 1 hour
)
```

Pattern: `S3KeySensor >> processing_task >> S3CopyObjectOperator` — wait for file, process it, archive it.

---

**Q9. How do you delete S3 objects after processing?**

Use `S3DeleteObjectsOperator`:

```python
from airflow.providers.amazon.aws.operators.s3 import S3DeleteObjectsOperator

cleanup = S3DeleteObjectsOperator(
    task_id="clean_staging",
    bucket="my-staging-bucket",
    keys=[
        "staging/{{ ds }}/raw.csv",
        "staging/{{ ds }}/metadata.json",
    ],
    aws_conn_id="aws_default",
)
```

For deleting many objects matching a prefix, use `prefix` instead of `keys`:
```python
S3DeleteObjectsOperator(
    task_id="clean_partition",
    bucket="my-bucket",
    prefix="staging/{{ ds }}/",   # deletes all objects under this prefix
    aws_conn_id="aws_default",
)
```

---

**Q10. How do you create an S3 bucket in a DAG if it may not exist yet?**

Use `S3CreateBucketOperator`. It is idempotent — it succeeds even if the bucket already exists:

```python
from airflow.providers.amazon.aws.operators.s3 import S3CreateBucketOperator

ensure_bucket = S3CreateBucketOperator(
    task_id="ensure_output_bucket",
    bucket_name="my-pipeline-output",
    region_name="us-east-1",
    aws_conn_id="aws_default",
)
```

Always put bucket creation as the first task when your pipeline depends on a specific bucket — it makes the pipeline self-contained and avoids "bucket not found" failures.

---

## Advanced Questions

**Q11. What is the difference between authenticating with IAM access keys vs an IAM role?**

| Method | How it works | When to use |
|---|---|---|
| Access key + secret | Static credentials stored in Airflow connection | Local development, third-party hosted Airflow |
| IAM Role (instance profile) | Airflow workers run on AWS with a role attached; credentials are auto-issued and rotated | Airflow on EC2, ECS, EKS (recommended for production) |
| IAM Role (web identity) | Used in EKS with IRSA (IAM Roles for Service Accounts) | Kubernetes-based Airflow on EKS |

IAM roles are strongly preferred in production:
- Credentials are temporary and auto-rotated
- No secrets to store, leak, or rotate manually
- Fine-grained permissions per service/environment

To use an IAM role in Airflow, create the AWS connection with no access key/secret — Airflow will fall back to the instance metadata service or environment credentials automatically.

---

**Q12. How do you handle cross-account S3 access in Airflow?**

Two approaches:

**Option 1 — Bucket policy on the target account**: The target S3 bucket grants access to the source account's IAM role. Configure the Airflow AWS connection with the source account's role — no special Airflow configuration needed.

**Option 2 — STS AssumeRole**: Use the `role_arn` extra in the Airflow AWS connection to assume a role in the target account:

```json
{
    "region_name": "us-east-1",
    "role_arn": "arn:aws:iam::TARGET_ACCOUNT_ID:role/AirflowCrossAccountRole",
    "role_session_name": "airflow-session"
}
```

When the S3 operator runs, Airflow calls `sts:AssumeRole` to get temporary credentials for the target account, then uses those for the S3 operation.

---

**Q13. How do you handle large files that might exceed memory limits in S3FileTransformOperator?**

`S3FileTransformOperator` downloads the entire file to the worker's local disk before transforming it. For very large files (tens of GBs), this can exhaust disk space or processing time.

Options for large files:
1. **Stream processing in the transform script** — process the file line by line, never loading it fully into memory
2. **Use S3 Select** via a custom PythonOperator + S3Hook — server-side filtering before download
3. **Use AWS Glue or EMR** via dedicated operators — offload the heavy processing to a scalable AWS service
4. **Use multipart download** and chunk processing in a custom PythonOperator with `boto3`

```python
# Streaming transform pattern in the transform script
import sys
import csv

with open(sys.argv[1], "r") as infile, open(sys.argv[2], "w") as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
    writer.writeheader()
    for row in reader:           # one row at a time — no memory explosion
        row["amount"] = float(row["amount"]) * 1.1
        writer.writerow(row)
```

---

**Q14. How do you pass an S3 key dynamically from an upstream task to an S3 operator?**

Use XCom to pass the key and Jinja to render it:

```python
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.s3 import S3CopyObjectOperator

def generate_key(**context):
    return f"processed/{context['ds']}/output_{context['run_id']}.csv"

generate = PythonOperator(task_id="generate_key", python_callable=generate_key)

archive = S3CopyObjectOperator(
    task_id="archive",
    source_bucket_name="my-bucket",
    source_bucket_key="{{ ti.xcom_pull(task_ids='generate_key') }}",   # XCom in Jinja
    dest_bucket_name="my-archive-bucket",
    dest_bucket_key="{{ ti.xcom_pull(task_ids='generate_key') | replace('processed', 'archive') }}",
    aws_conn_id="aws_default",
)
generate >> archive
```

---

**Q15. What IAM permissions are needed for common S3 operator usage?**

Minimum permissions for a typical upload-copy-delete pipeline:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:CreateBucket"
    ],
    "Resource": [
      "arn:aws:s3:::my-bucket-name",
      "arn:aws:s3:::my-bucket-name/*"
    ]
  }]
}
```

For cross-account copy, also add `s3:GetObjectAcl` and `s3:PutObjectAcl`. For S3KeySensor, `s3:ListBucket` is sufficient if checking existence.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [03_PostgresOperator](../03_PostgresOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [05_HttpOperator](../05_HttpOperator/Theory.md)
