# Object Storage API — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Airflow on Cloud](../../06_Airflow_on_Cloud/Readme.md)**

---

## Q1: What is ObjectStoragePath in Airflow 3?

`ObjectStoragePath` is an Airflow 3 API that provides a **unified, backend-agnostic file system interface** modelled after Python's standard `pathlib.Path`. It lets you read, write, list, copy, and move files using the same Python code regardless of whether the data lives in Amazon S3, Google Cloud Storage, Azure Blob Storage, or the local file system.

```python
from airflow.io.path import ObjectStoragePath

# The same API works for all backends — only the URI changes
s3_path  = ObjectStoragePath("s3://bucket/file.parquet",  conn_id="aws_default")
gcs_path = ObjectStoragePath("gs://bucket/file.parquet",  conn_id="gcs_default")
local    = ObjectStoragePath("file:///opt/airflow/data/file.parquet")

# Identical method call for all three
content = s3_path.read_bytes()
content = gcs_path.read_bytes()
content = local.read_bytes()
```

---

## Q2: What problem does ObjectStoragePath solve compared to using boto3 or the GCS client directly?

Before `ObjectStoragePath`, DAG code was tightly coupled to specific storage backends:

```python
# boto3 (S3-specific)
import boto3
s3 = boto3.client("s3")
obj = s3.get_object(Bucket="my-bucket", Key="data/file.csv")
content = obj["Body"].read()

# google-cloud-storage (GCS-specific)
from google.cloud import storage
client = storage.Client()
blob = client.bucket("my-bucket").blob("data/file.csv")
content = blob.download_as_bytes()
```

Problems with this approach:
1. **Vendor lock-in in DAG code** — migrating from S3 to GCS means rewriting DAG logic
2. **Credential management** — each library has its own auth config, separate from Airflow connections
3. **Inconsistent APIs** — you must remember different method names for each backend
4. **Testing difficulty** — you need different mocks for each backend

`ObjectStoragePath` solves all of these: one API, backed by Airflow connections (which you already manage), with consistent behavior across backends.

---

## Q3: How does ObjectStoragePath use Airflow Connections for authentication?

Every `ObjectStoragePath` accepts a `conn_id` parameter that references an Airflow Connection. The connection holds the credentials for the storage backend. `ObjectStoragePath` delegates all authentication to the relevant Airflow provider hook.

```python
# conn_id="aws_default" → Airflow looks up the "aws_default" connection
# → that connection has your AWS credentials / IAM role config
# → boto3 is initialized with those credentials behind the scenes
path = ObjectStoragePath("s3://bucket/file.csv", conn_id="aws_default")
```

Benefits:
- Credentials are stored in Airflow's secure connection store (or Secrets Backend)
- No hardcoded secrets in DAG files
- Rotating credentials only requires updating the Airflow connection — no DAG code changes
- Works with all Airflow secrets backends (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager)

---

## Q4: How do you read a Parquet file from S3 into a Pandas DataFrame?

```python
from airflow.io.path import ObjectStoragePath
import pandas as pd
from io import BytesIO

def read_parquet_from_s3(s3_uri: str) -> pd.DataFrame:
    path = ObjectStoragePath(s3_uri, conn_id="aws_default")

    # Method 1: read as bytes, wrap in BytesIO
    raw_bytes = path.read_bytes()
    df = pd.read_parquet(BytesIO(raw_bytes))
    return df

    # Method 2: open as file-like object (better for large files)
    with path.open("rb") as f:
        df = pd.read_parquet(f)
    return df
```

---

## Q5: What path operations are supported?

`ObjectStoragePath` supports the full `pathlib`-style API:

| Operation | Method | Example |
|-----------|--------|---------|
| Read bytes | `.read_bytes()` | `path.read_bytes()` |
| Read text | `.read_text()` | `path.read_text(encoding="utf-8")` |
| Write bytes | `.write_bytes(data)` | `path.write_bytes(b"data")` |
| Write text | `.write_text(text)` | `path.write_text("hello")` |
| Open file | `.open(mode)` | `with path.open("rb") as f:` |
| Check exists | `.exists()` | `if path.exists():` |
| List directory | `.iterdir()` | `for f in prefix.iterdir():` |
| Glob | `.glob(pattern)` | `prefix.glob("**/*.csv")` |
| Copy | `.copy(dst)` | `path.copy(dst_path)` |
| Move | `.move(dst)` | `path.move(dst_path)` |
| Delete | `.unlink()` | `path.unlink()` |
| File name | `.name` | `path.name` → `"file.csv"` |
| Parent path | `.parent` | `path.parent` |
| Join paths | `/` operator | `base / "subdir" / "file.csv"` |
| Stat/metadata | `.stat()` | `path.stat().st_size` |

---

## Q6: Can you copy a file from S3 directly to GCS using ObjectStoragePath?

Yes. Cross-backend copies are supported. `ObjectStoragePath` reads from the source backend and writes to the destination backend transparently:

```python
from airflow.io.path import ObjectStoragePath

def copy_s3_to_gcs(filename: str):
    src = ObjectStoragePath(f"s3://raw-bucket/{filename}",   conn_id="aws_default")
    dst = ObjectStoragePath(f"gs://archive-bucket/{filename}", conn_id="gcs_default")

    src.copy(dst)
    print(f"Copied {filename} from S3 to GCS")
```

Under the hood, Airflow downloads the bytes from S3 using the S3 hook and uploads them to GCS using the GCS hook. For very large files (multi-GB), consider using provider-native multipart transfer instead, as this in-memory approach requires holding the whole file in the worker's RAM.

---

## Q7: How does ObjectStoragePath compare to the S3Hook and GCSHook directly?

| | `S3Hook` / `GCSHook` | `ObjectStoragePath` |
|--|---------------------|---------------------|
| **Abstraction level** | Backend-specific | Backend-agnostic |
| **API style** | Hook methods (`download_file`, `load_file`, etc.) | `pathlib`-like (`.read_bytes()`, `.write_text()`) |
| **Cross-backend copy** | Manual (download then upload) | Built-in `.copy()` |
| **Provider-specific features** | Full access (e.g., S3 multipart, GCS resumable upload) | Common subset only |
| **Code portability** | Low — switching backends requires rewriting | High — change URI only |
| **When to use** | Need provider-specific features (presigned URLs, ACLs, etc.) | Standard file I/O operations |

Use `ObjectStoragePath` for the common 80% of use cases. Drop down to `S3Hook`/`GCSHook` when you need provider-specific features like signed URLs, metadata tagging, ACLs, or server-side encryption settings.

---

## Q8: How do you list all files in an S3 prefix and process each one?

```python
from airflow.io.path import ObjectStoragePath
from airflow.decorators import task

@task
def process_daily_files(**context):
    ds = context["ds"]

    # Define the prefix for today's files
    prefix = ObjectStoragePath(f"s3://raw-bucket/ingest/{ds}/", conn_id="aws_default")

    if not prefix.exists():
        print(f"No data directory found for {ds}")
        return []

    processed = []
    for file_path in prefix.glob("*.json"):
        print(f"Processing: {file_path.name}")

        # Read the file
        content = file_path.read_text(encoding="utf-8")

        # Write processed version to a different location
        dest = ObjectStoragePath(
            f"s3://processed-bucket/output/{ds}/{file_path.name}",
            conn_id="aws_default"
        )
        dest.write_text(content.upper(), encoding="utf-8")
        processed.append(str(file_path))

    print(f"Processed {len(processed)} files")
    return processed
```

---

## Q9: How do you migrate DAG code from boto3 to ObjectStoragePath?

A practical before/after migration:

**Before (boto3):**
```python
import boto3
import json

def old_process():
    s3 = boto3.client("s3", region_name="us-east-1")

    # Read
    response = s3.get_object(Bucket="my-bucket", Key="data/config.json")
    config = json.loads(response["Body"].read().decode("utf-8"))

    # Write
    result = json.dumps({"status": "done"})
    s3.put_object(Bucket="my-bucket", Key="data/result.json", Body=result.encode())

    # Check exists
    try:
        s3.head_object(Bucket="my-bucket", Key="data/config.json")
        exists = True
    except s3.exceptions.ClientError:
        exists = False
```

**After (ObjectStoragePath):**
```python
from airflow.io.path import ObjectStoragePath
import json

BASE = ObjectStoragePath("s3://my-bucket/data/", conn_id="aws_default")

def new_process():
    config_path = BASE / "config.json"

    # Read
    config = json.loads(config_path.read_text(encoding="utf-8"))

    # Write
    result_path = BASE / "result.json"
    result_path.write_text(json.dumps({"status": "done"}), encoding="utf-8")

    # Check exists
    exists = config_path.exists()
```

The `ObjectStoragePath` version is shorter, more readable, and works without changes if you swap the URI to `gs://` or `abfs://`.

---

## Q10: What are the limitations of ObjectStoragePath?

**1. No provider-specific features:** `ObjectStoragePath` exposes a common subset of operations. S3 presigned URLs, GCS signed URLs, Azure SAS tokens, ACL management, and custom metadata tagging are not available through this API — use the provider hooks directly for those.

**2. In-memory cross-backend copies:** `.copy()` across backends reads the entire file into worker memory before writing to the destination. For multi-GB files, use provider-native transfer tools.

**3. No atomic operations:** Object storage backends (S3, GCS) do not support transactions. There is no `.rename()` that is guaranteed atomic — `.move()` is a copy-then-delete.

**4. Provider package required:** Each backend requires its corresponding provider package installed on all workers that will access it. The `ObjectStoragePath` class itself is in `apache-airflow` core, but the backend implementations live in provider packages.

**5. No streaming uploads for all backends:** Streaming upload support (opening a file for writing and streaming bytes into it) varies by provider. For large uploads, writing to a temp file and then uploading may be more reliable.

---

## Q11: How does ObjectStoragePath integrate with Airflow's connection management in practice?

A recommended pattern for production DAGs:

```python
# dags/shared/storage.py — centralize all storage path definitions
from airflow.io.path import ObjectStoragePath

# Define base paths once — import these everywhere
RAW_BUCKET       = ObjectStoragePath("s3://company-raw/",       conn_id="aws_prod")
PROCESSED_BUCKET = ObjectStoragePath("s3://company-processed/", conn_id="aws_prod")
ARCHIVE_BUCKET   = ObjectStoragePath("gs://company-archive/",   conn_id="gcs_prod")

def raw_path(ds: str, filename: str) -> ObjectStoragePath:
    return RAW_BUCKET / ds / filename

def processed_path(ds: str, filename: str) -> ObjectStoragePath:
    return PROCESSED_BUCKET / ds / filename
```

Usage in DAGs:
```python
from shared.storage import raw_path, processed_path

@task
def transform(**context):
    src = raw_path(context["ds"], "orders.csv")
    dst = processed_path(context["ds"], "orders.parquet")

    df = pd.read_csv(src.open("rb"))
    # ... transform ...
    dst.write_bytes(df_to_parquet_bytes(df))
```

This pattern means that changing storage backends (e.g., migrating from S3 to GCS) only requires updating `shared/storage.py` — not every DAG file.

---

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Airflow on Cloud](../../06_Airflow_on_Cloud/Readme.md)**
