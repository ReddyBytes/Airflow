# Object Storage API — Cheatsheet

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**

---

## What is ObjectStoragePath?

`ObjectStoragePath` is an Airflow 3 abstraction modelled after Python's `pathlib.Path`. It provides a **single API for reading, writing, listing, and moving files** across S3, GCS, Azure Blob Storage, and local file systems.

```python
from airflow.io.path import ObjectStoragePath

# S3
path = ObjectStoragePath("s3://my-bucket/data/file.csv", conn_id="aws_default")

# GCS
path = ObjectStoragePath("gs://my-bucket/data/file.csv", conn_id="gcs_default")

# Azure Blob
path = ObjectStoragePath("abfs://container@account.dfs.core.windows.net/file.csv", conn_id="azure_data_lake")

# Local
path = ObjectStoragePath("file:///opt/airflow/data/file.csv")
```

Swap the URI — the same method calls work against any backend.

---

## Supported Backends

| Backend | URI Scheme | Required Provider |
|---------|-----------|------------------|
| Amazon S3 | `s3://bucket/key` | `apache-airflow-providers-amazon` |
| Google Cloud Storage | `gs://bucket/object` | `apache-airflow-providers-google` |
| Azure Blob / ADLS Gen2 | `abfs://container@account.dfs.core.windows.net/blob` | `apache-airflow-providers-microsoft-azure` |
| Local file system | `file:///absolute/path` | Built-in (no provider needed) |
| SFTP / FTP | `sftp://host/path` | `apache-airflow-providers-sftp` |

---

## Path Operations Reference

### Reading

```python
from airflow.io.path import ObjectStoragePath

path = ObjectStoragePath("s3://bucket/data/file.csv", conn_id="aws_default")

# Read entire file as bytes
raw: bytes = path.read_bytes()

# Read entire file as text
text: str = path.read_text(encoding="utf-8")

# Open as file-like object (supports pandas, csv.reader, etc.)
with path.open("rb") as f:
    df = pd.read_csv(f)

# Open in text mode
with path.open("r", encoding="utf-8") as f:
    for line in f:
        print(line.strip())
```

### Writing

```python
# Write bytes
path.write_bytes(b"hello world")

# Write text
path.write_text("hello world", encoding="utf-8")

# Open for writing (streaming — memory-efficient for large files)
with path.open("wb") as f:
    f.write(b"chunk 1")
    f.write(b"chunk 2")
```

### Checking existence and metadata

```python
# Does the file exist?
if path.exists():
    print("File found")

# Is it a file (not a directory/prefix)?
path.is_file()   # True

# Is it a directory/prefix?
path.is_dir()    # False for objects, True for prefixes

# Get file size in bytes
stat = path.stat()
print(stat.st_size)

# Get modification time
print(stat.st_mtime)
```

### Listing

```python
prefix = ObjectStoragePath("s3://bucket/data/", conn_id="aws_default")

# List direct children (non-recursive)
for item in prefix.iterdir():
    print(item)

# Recursive glob — all CSV files anywhere under the prefix
for csv_file in prefix.glob("**/*.csv"):
    print(csv_file)

# List only files matching a pattern
for parquet_file in prefix.glob("*.parquet"):
    print(parquet_file)
```

### Path manipulation (like pathlib)

```python
path = ObjectStoragePath("s3://bucket/data/2026/03/file.csv", conn_id="aws_default")

path.name          # "file.csv"
path.stem          # "file"
path.suffix        # ".csv"
path.parent        # ObjectStoragePath("s3://bucket/data/2026/03/")
path.parts         # ("s3://bucket/", "data", "2026", "03", "file.csv")

# Build a new path from components
new_path = path.parent / "processed" / "file_processed.parquet"
# → s3://bucket/data/2026/03/processed/file_processed.parquet
```

### Copying and moving

```python
src = ObjectStoragePath("s3://raw-bucket/file.csv", conn_id="aws_default")
dst = ObjectStoragePath("s3://processed-bucket/file.csv", conn_id="aws_default")

# Copy within same backend
src.copy(dst)

# Move (copy then delete source)
src.move(dst)

# Cross-backend copy (S3 → GCS) — reads bytes, writes to destination
src_s3  = ObjectStoragePath("s3://raw-bucket/file.csv", conn_id="aws_default")
dst_gcs = ObjectStoragePath("gs://archive-bucket/file.csv", conn_id="gcs_default")
src_s3.copy(dst_gcs)
```

---

## Connection Configuration

### S3 Connection

```
Conn ID:   aws_default
Conn Type: Amazon Web Services
Extra:     {"region_name": "us-east-1"}
```

Or via environment variable:
```bash
AIRFLOW_CONN_AWS_DEFAULT='{"conn_type": "aws", "extra": {"region_name": "us-east-1"}}'
```

For IAM role-based auth (EC2/ECS), leave credentials empty — boto3 picks up the instance role automatically.

### GCS Connection

```
Conn ID:   gcs_default
Conn Type: Google Cloud
Keyfile JSON: <paste service account JSON>
```

```bash
AIRFLOW_CONN_GCS_DEFAULT='{"conn_type": "google_cloud_platform", "extra": {"key_path": "/secrets/sa.json"}}'
```

### Azure Blob / ADLS Connection

```
Conn ID:   azure_data_lake
Conn Type: Azure Data Lake Storage
Account Name: mystorageaccount
Extra: {"account_key": "your_key"}
```

---

## S3 — ObjectStoragePath Examples

```python
from airflow.io.path import ObjectStoragePath
import pandas as pd
from io import BytesIO

# ── Read a CSV from S3 into a DataFrame ──────────────────────────────────────
def read_s3_csv():
    path = ObjectStoragePath("s3://my-bucket/sales/2026-03-15.csv", conn_id="aws_default")
    with path.open("rb") as f:
        df = pd.read_csv(f)
    return df

# ── Write a DataFrame to S3 as Parquet ───────────────────────────────────────
def write_s3_parquet(df: pd.DataFrame):
    path = ObjectStoragePath("s3://my-bucket/processed/2026-03-15.parquet", conn_id="aws_default")
    buf = BytesIO()
    df.to_parquet(buf, index=False)
    path.write_bytes(buf.getvalue())

# ── List all files in an S3 prefix for a given date ──────────────────────────
def list_s3_prefix(date: str):
    prefix = ObjectStoragePath(f"s3://my-bucket/raw/{date}/", conn_id="aws_default")
    return [str(p) for p in prefix.iterdir() if p.is_file()]
```

---

## GCS — ObjectStoragePath Examples

```python
from airflow.io.path import ObjectStoragePath

# ── Check if a GCS file exists before processing ─────────────────────────────
def check_gcs_file(date: str) -> bool:
    path = ObjectStoragePath(
        f"gs://data-lake/daily/{date}/export.parquet",
        conn_id="gcs_default"
    )
    return path.exists()

# ── Copy file from GCS to S3 ─────────────────────────────────────────────────
def replicate_gcs_to_s3(filename: str):
    src = ObjectStoragePath(f"gs://source-bucket/{filename}", conn_id="gcs_default")
    dst = ObjectStoragePath(f"s3://target-bucket/{filename}", conn_id="aws_default")
    # ObjectStoragePath handles cross-backend copy transparently
    src.copy(dst)
    print(f"Copied {filename}: GCS → S3")

# ── Write text report to GCS ─────────────────────────────────────────────────
def write_report(content: str, date: str):
    path = ObjectStoragePath(
        f"gs://reports-bucket/daily/{date}/report.txt",
        conn_id="gcs_default"
    )
    path.write_text(content, encoding="utf-8")
```

---

## Using ObjectStoragePath in a DAG

```python
from airflow.sdk import DAG
from airflow.decorators import task
from airflow.io.path import ObjectStoragePath
from datetime import datetime

RAW_PATH       = ObjectStoragePath("s3://raw-bucket/",       conn_id="aws_default")
PROCESSED_PATH = ObjectStoragePath("gs://processed-bucket/", conn_id="gcs_default")

with DAG(
    dag_id="s3_to_gcs_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    @task
    def process_files(**context):
        ds = context["ds"]
        prefix = RAW_PATH / ds / ""

        processed_count = 0
        for raw_file in prefix.glob("*.csv"):
            # Read from S3
            content = raw_file.read_text(encoding="utf-8")

            # Write to GCS (cross-backend)
            dest = PROCESSED_PATH / ds / raw_file.name.replace(".csv", ".txt")
            dest.write_text(content.upper(), encoding="utf-8")
            processed_count += 1

        print(f"Processed {processed_count} files: S3 → GCS")
        return processed_count

    process_files()
```

---

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**
