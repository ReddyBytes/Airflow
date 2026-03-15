# Object Storage in Airflow 3

## Navigation
⬅️ **Prev: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## The Story

In Airflow 2, reading a file from S3 meant importing boto3. Reading from GCS meant importing the Google Cloud Storage client. Reading from Azure Blob meant the Azure SDK. Every provider had its own API, its own auth pattern, its own error handling. Your DAG code was coupled to the storage backend.

In Airflow 3, you can store and access files directly using a unified `ObjectStoragePath` API — whether they're on local filesystem, S3, GCS, or Azure Blob. Your code stays the same. Only the connection changes. Write your DAG against `ObjectStoragePath`, point it at S3 in production, and point it at local filesystem in tests. No code change required.

---

## The ObjectStoragePath API

`airflow.io.path.ObjectStoragePath` is the central class. It behaves like Python's `pathlib.Path` — familiar, composable, and chainable — but works across any supported storage backend.

```python
from airflow.io.path import ObjectStoragePath

# S3
s3_path = ObjectStoragePath("s3://my-bucket/data/file.csv", conn_id="aws_default")

# GCS
gcs_path = ObjectStoragePath("gs://my-bucket/data/file.csv", conn_id="google_cloud_default")

# Azure Blob Storage
azure_path = ObjectStoragePath("abfs://container/data/file.csv", conn_id="azure_default")

# Local filesystem (no conn_id needed)
local_path = ObjectStoragePath("file:///tmp/data/file.csv")
```

The API is the same regardless of backend. The `conn_id` parameter tells Airflow which connection to use for authentication.

---

## Supported Backends

| Storage | URI Scheme | Provider Package |
|---------|-----------|-----------------|
| Amazon S3 | `s3://` | `apache-airflow-providers-amazon` |
| Google Cloud Storage | `gs://` or `gcs://` | `apache-airflow-providers-google` |
| Azure Blob Storage | `abfs://` | `apache-airflow-providers-microsoft-azure` |
| Local Filesystem | `file:///` | Built-in |
| SFTP/SSH | `sftp://` | `apache-airflow-providers-sftp` |
| HTTP/HTTPS | `http://`, `https://` | Built-in |

---

## Core Operations

### Reading Files

```python
from airflow.io.path import ObjectStoragePath

# Read as bytes
path = ObjectStoragePath("s3://bucket/data/report.csv", conn_id="aws_default")
content: bytes = path.read_bytes()

# Read as text
text: str = path.read_text(encoding="utf-8")

# Read as Pandas DataFrame
import pandas as pd
import io

df = pd.read_csv(io.BytesIO(path.read_bytes()))

# Read parquet directly
df = pd.read_parquet(path)   # pandas supports pathlib-compatible objects

# Stream large files
with path.open("rb") as f:
    for chunk in iter(lambda: f.read(8192), b""):
        process_chunk(chunk)
```

### Writing Files

```python
from airflow.io.path import ObjectStoragePath
import pandas as pd

path = ObjectStoragePath("s3://bucket/output/data.parquet", conn_id="aws_default")

# Write bytes
path.write_bytes(b"raw content here")

# Write text
path.write_text("hello world\nline 2\n", encoding="utf-8")

# Write pandas DataFrame
df = pd.DataFrame({"col": [1, 2, 3]})

# As CSV
path_csv = ObjectStoragePath("s3://bucket/output/data.csv", conn_id="aws_default")
path_csv.write_text(df.to_csv(index=False))

# As parquet
path_parquet = ObjectStoragePath("s3://bucket/output/data.parquet", conn_id="aws_default")
buffer = io.BytesIO()
df.to_parquet(buffer)
path_parquet.write_bytes(buffer.getvalue())

# Using open() for streaming writes
with path.open("wb") as f:
    f.write(b"streaming content")
```

### Navigating Paths (pathlib-style)

```python
from airflow.io.path import ObjectStoragePath

base = ObjectStoragePath("s3://bucket/data/", conn_id="aws_default")

# Join paths with /
daily_dir = base / "2024" / "03" / "15"
# → s3://bucket/data/2024/03/15/

# Get file name
path = ObjectStoragePath("s3://bucket/data/report.csv", conn_id="aws_default")
print(path.name)       # "report.csv"
print(path.stem)       # "report"
print(path.suffix)     # ".csv"
print(path.parent)     # s3://bucket/data/

# List directory contents
for item in base.iterdir():
    print(item)

# Check existence
if path.exists():
    size = path.stat().st_size
    print(f"File size: {size} bytes")

# Create directories
(base / "new_dir").mkdir(exist_ok=True)
```

### Copying Between Backends

The ObjectStoragePath API supports cross-backend copies. Airflow handles the streaming transfer:

```python
from airflow.io.path import ObjectStoragePath

# Copy from S3 to GCS
source = ObjectStoragePath("s3://source-bucket/data/file.parquet", conn_id="aws_default")
destination = ObjectStoragePath("gs://dest-bucket/data/file.parquet", conn_id="google_cloud_default")

# Method 1: Read and write
destination.write_bytes(source.read_bytes())

# Method 2: Using shutil-style copy (if available for the backend)
source.copy(destination)

# Method 3: Stream copy for large files
import shutil
with source.open("rb") as src, destination.open("wb") as dst:
    shutil.copyfileobj(src, dst)
```

---

## Using ObjectStoragePath in Operators

### In PythonOperator / @task

```python
from airflow import DAG
from airflow.decorators import task
from airflow.io.path import ObjectStoragePath
from datetime import datetime

with DAG(
    dag_id="file_processing",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
) as dag:

    @task
    def process_daily_file(**context) -> dict:
        ds = context["ds"]   # e.g., "2024-03-15"

        # Path parameterized by date
        input_path = ObjectStoragePath(
            f"s3://data-lake/raw/{ds}/transactions.csv",
            conn_id="aws_default",
        )
        output_path = ObjectStoragePath(
            f"s3://data-lake/processed/{ds}/transactions.parquet",
            conn_id="aws_default",
        )

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Read input
        import pandas as pd
        import io
        df = pd.read_csv(io.BytesIO(input_path.read_bytes()))

        # Process
        df = df.dropna(subset=["transaction_id", "amount"])
        df["amount"] = df["amount"].abs()

        # Write output
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        output_path.write_bytes(buffer.getvalue())

        return {
            "input": str(input_path),
            "output": str(output_path),
            "rows": len(df),
        }

    process_daily_file()
```

### vs boto3 / Direct SDK (Why ObjectStoragePath is Better)

```python
# Old approach (Airflow 2) — coupled to S3 / boto3
import boto3

def read_from_s3(bucket: str, key: str) -> bytes:
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()

# Problems:
# 1. Only works with S3 — GCS requires completely different code
# 2. Auth is configured outside Airflow (env vars, IAM role)
# 3. No integration with Airflow connections
# 4. Can't mock easily in tests

# New approach (Airflow 3) — backend-agnostic
from airflow.io.path import ObjectStoragePath

def read_file(path_uri: str, conn_id: str) -> bytes:
    return ObjectStoragePath(path_uri, conn_id=conn_id).read_bytes()

# Benefits:
# 1. Works with S3, GCS, Azure, local — same code
# 2. Auth configured in Airflow connections UI
# 3. Easy to mock: swap conn_id for tests, use file:// URI locally
# 4. pathlib-compatible — familiar API
```

---

## Comparison with Direct Backend APIs

| Feature | boto3 (S3 direct) | ObjectStoragePath |
|---------|------------------|------------------|
| Backend support | S3 only | S3, GCS, Azure, local, SFTP |
| Auth management | AWS credentials, IAM | Airflow connections |
| Code change to switch backends | Full rewrite | Change URI scheme + conn_id |
| Pathlib compatibility | No | Yes |
| Available in tests with local files | Requires mock | Use `file://` URI — no mock needed |
| Cross-backend copy | Manual streaming | `source.copy(dest)` |
| Directory listing | `list_objects_v2` | `path.iterdir()` |
| File exists check | Try/except or HeadObject | `path.exists()` |

---

## Environment-Aware Paths (Dev vs Prod Pattern)

```python
# config/storage_config.py
import os

ENVIRONMENT = os.getenv("AIRFLOW_ENV", "development")

def get_data_path(relative_path: str):
    """Returns ObjectStoragePath appropriate for the environment."""
    from airflow.io.path import ObjectStoragePath

    if ENVIRONMENT == "production":
        return ObjectStoragePath(
            f"s3://prod-data-lake/{relative_path}",
            conn_id="aws_prod",
        )
    elif ENVIRONMENT == "staging":
        return ObjectStoragePath(
            f"s3://staging-data-lake/{relative_path}",
            conn_id="aws_staging",
        )
    else:
        # Development: use local filesystem — no AWS credentials needed
        return ObjectStoragePath(
            f"file:///tmp/airflow_dev_data/{relative_path}"
        )

# Usage in DAG:
# path = get_data_path("2024/03/15/transactions.csv")
# df = pd.read_csv(io.BytesIO(path.read_bytes()))
# Works identically in dev (local file) and prod (S3)
```

---

## Navigation
⬅️ **Prev: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**
