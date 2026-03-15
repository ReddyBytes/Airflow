# S3 Operators — Theory

## Your Pipeline in the Cloud

Your pipeline has processed the data. Now what? In most modern data stacks, the answer is S3. Processed files go to S3 for downstream consumers. Reports get archived in S3. Raw data lands in S3 before being loaded into a data warehouse.

**S3 operators let you read, write, and move files between local storage and AWS S3 — or between S3 buckets — directly from your DAG tasks.**

Think of it like a logistics team. Your pipeline produces boxes (files), and the S3 operators are the forklift operators who move those boxes to the right warehouse shelf (S3 key/prefix). They know the routes, handle the paperwork (authentication), and deal with heavy loads (large files, multipart uploads).

---

## Prerequisites: Setting Up the AWS Connection

Before you can use any S3 operator, you need to configure AWS credentials in Airflow.

### Step 1: Install the Amazon provider

```bash
pip install apache-airflow-providers-amazon
```

### Step 2: Add the AWS connection in the Airflow UI

1. Go to **Admin → Connections**
2. Click **+** to add a new connection
3. Fill in:

| Field | Value |
|---|---|
| Connection Id | `aws_default` (used by default in most S3 operators) |
| Connection Type | `Amazon Web Services` |
| AWS Access Key ID | Your IAM access key |
| AWS Secret Access Key | Your IAM secret key |
| Extra | `{"region_name": "us-east-1"}` |

### Or use an environment variable:

```bash
export AIRFLOW_CONN_AWS_DEFAULT='{"conn_type": "aws", "login": "AKIAIOSFODNN7EXAMPLE", "password": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "extra": {"region_name": "us-east-1"}}'
```

### Or use IAM Role (recommended for EC2/ECS/EKS):

If your Airflow workers run on AWS with an IAM role attached, you can leave credentials blank and rely on the role. Set `Connection Type = Amazon Web Services` with no Access Key — it will use the instance profile automatically.

---

## IAM Permissions Required

Your IAM user or role needs at minimum:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:CreateBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name",
        "arn:aws:s3:::your-bucket-name/*"
      ]
    }
  ]
}
```

---

## Key S3 Operators

### LocalFilesystemToS3Operator

Uploads a file from the local filesystem (or Airflow worker) to S3:

```python
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator

upload_report = LocalFilesystemToS3Operator(
    task_id="upload_report_to_s3",
    filename="/tmp/reports/daily_{{ ds }}.csv",   # Local file path
    dest_key="reports/daily/{{ ds }}/report.csv",  # S3 key (path in bucket)
    dest_bucket="my-data-bucket",                  # S3 bucket name
    aws_conn_id="aws_default",
    replace=True,  # Overwrite if key already exists
)
```

### S3CreateBucketOperator

Creates an S3 bucket if it doesn't already exist:

```python
from airflow.providers.amazon.aws.operators.s3 import S3CreateBucketOperator

create_bucket = S3CreateBucketOperator(
    task_id="create_output_bucket",
    bucket_name="my-pipeline-output",
    region_name="us-east-1",
    aws_conn_id="aws_default",
)
```

### S3CopyObjectOperator

Copies an S3 object from one key to another (within or across buckets):

```python
from airflow.providers.amazon.aws.operators.s3 import S3CopyObjectOperator

copy_to_archive = S3CopyObjectOperator(
    task_id="archive_processed_file",
    source_bucket_name="my-staging-bucket",
    source_bucket_key="staging/{{ ds }}/data.csv",
    dest_bucket_name="my-archive-bucket",
    dest_bucket_key="archive/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
)
```

### S3DeleteObjectsOperator

Deletes objects from S3 (cleanup after processing):

```python
from airflow.providers.amazon.aws.operators.s3 import S3DeleteObjectsOperator

cleanup_staging = S3DeleteObjectsOperator(
    task_id="clean_up_staging",
    bucket="my-staging-bucket",
    keys=["staging/{{ ds }}/data.csv", "staging/{{ ds }}/metadata.json"],
    aws_conn_id="aws_default",
)
```

### S3FileTransformOperator

Downloads a file from S3, runs a transformation script on it, and uploads the result back to S3:

```python
from airflow.providers.amazon.aws.operators.s3 import S3FileTransformOperator

transform_file = S3FileTransformOperator(
    task_id="transform_s3_file",
    source_s3_key="s3://my-bucket/raw/{{ ds }}/data.csv",
    dest_s3_key="s3://my-bucket/processed/{{ ds }}/data.csv",
    transform_script="/opt/airflow/scripts/transform.py",
    aws_conn_id="aws_default",
)
```

---

## Full Working Code Example

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.operators.s3 import (
    S3CreateBucketOperator,
    S3CopyObjectOperator,
)
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator

BUCKET = "my-pipeline-data"
AWS_CONN = "aws_default"

with DAG(
    dag_id="s3_operator_example",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
) as dag:

    # Ensure bucket exists
    ensure_bucket = S3CreateBucketOperator(
        task_id="ensure_bucket_exists",
        bucket_name=BUCKET,
        region_name="us-east-1",
        aws_conn_id=AWS_CONN,
    )

    # Generate a local file (in real life, this would be your processing task)
    generate_report = BashOperator(
        task_id="generate_daily_report",
        bash_command="""
            mkdir -p /tmp/reports/{{ ds }}
            echo "date,orders,revenue" > /tmp/reports/{{ ds }}/summary.csv
            echo "{{ ds }},142,15234.50" >> /tmp/reports/{{ ds }}/summary.csv
        """,
    )

    # Upload the generated file to S3
    upload_report = LocalFilesystemToS3Operator(
        task_id="upload_report_to_s3",
        filename="/tmp/reports/{{ ds }}/summary.csv",
        dest_key="reports/daily/{{ ds }}/summary.csv",
        dest_bucket=BUCKET,
        aws_conn_id=AWS_CONN,
        replace=True,
    )

    # Archive it to a separate bucket
    archive_report = S3CopyObjectOperator(
        task_id="archive_report",
        source_bucket_name=BUCKET,
        source_bucket_key="reports/daily/{{ ds }}/summary.csv",
        dest_bucket_name=BUCKET,
        dest_bucket_key="archive/{{ macros.ds_format(ds, '%Y-%m-%d', '%Y/%m/%d') }}/summary.csv",
        aws_conn_id=AWS_CONN,
    )

    ensure_bucket >> generate_report >> upload_report >> archive_report
```

---

## When to Use S3 Operators

**Good for:**
- Uploading pipeline outputs to S3 for downstream consumers
- Archiving processed files
- Moving data between S3 buckets (raw → processed → archive)
- Triggering downstream pipelines that read from S3
- Data lake workflows

**Not ideal for:**
- Very large files that need streaming (consider `S3FileTransformOperator` or custom code)
- Real-time streaming data (use Kinesis or Kafka)

---

## Navigation

**Prev:** [PostgresOperator Theory](../03_PostgresOperator/Theory.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [TriggerDagRunOperator Theory](../05_TriggerDagRunOperator/Theory.md)
