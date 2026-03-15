# S3KeySensor — Cheatsheet

## Quick Reference: Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `bucket_key` | `str \| list[str]` | required | S3 key(s) to check. Supports Jinja. Use full `s3://` URI or key path + `bucket_name`. |
| `bucket_name` | `str` | `None` | S3 bucket name. Not needed if `bucket_key` contains the full `s3://` URI. |
| `aws_conn_id` | `str` | `"aws_default"` | Airflow Connection ID for AWS credentials |
| `wildcard_match` | `bool` | `False` | Treat `bucket_key` as a glob pattern (matches any key fitting the pattern) |
| `verify` | `bool \| str` | `None` | SSL verification: `True`/`False` or path to CA bundle |
| `check_fn` | `Callable` | `None` | Optional: `(list[dict]) -> bool`. Validate found objects beyond existence. |
| `poke_interval` | `float` | `60` | Seconds between S3 checks |
| `timeout` | `float` | `604800` (7 days) | Max seconds before task fails or skips |
| `mode` | `str` | `"poke"` | `"poke"` or `"reschedule"` |
| `deferrable` | `bool` | `False` | Use async Triggerer (recommended for Airflow 3 long waits) |
| `soft_fail` | `bool` | `False` | Skip instead of fail on timeout |

---

## Import

```python
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
```

**Provider install:**
```bash
pip install apache-airflow-providers-amazon
```

---

## bucket_key Format Options

```python
# Full S3 URI — most explicit
bucket_key="s3://my-bucket/data/2024-01-15/orders.csv"

# Key only (requires bucket_name separately)
bucket_name="my-bucket"
bucket_key="data/2024-01-15/orders.csv"

# With Jinja date templating
bucket_key="s3://my-bucket/data/{{ ds }}/orders.csv"
bucket_key="s3://my-bucket/data/{{ ds_nodash }}/orders.csv"  # No dashes: 20240115

# Wildcard (requires wildcard_match=True)
bucket_key="s3://my-bucket/data/{{ ds }}/part-*.parquet"

# Multiple exact keys (all must exist)
bucket_key=[
    "s3://my-bucket/data/{{ ds }}/part-000.parquet",
    "s3://my-bucket/data/{{ ds }}/part-001.parquet",
    "s3://my-bucket/data/{{ ds }}/_SUCCESS",
]
```

---

## Code Patterns

### Pattern 1: Wait for a Single File (Production)

```python
S3KeySensor(
    task_id="wait_for_daily_delivery",
    bucket_key="s3://vendor-bucket/daily/{{ ds }}/orders.csv",
    aws_conn_id="aws_default",
    poke_interval=300,       # Check every 5 minutes
    timeout=8 * 60 * 60,     # Give up after 8 hours
    mode="reschedule",
    soft_fail=False,
)
```

---

### Pattern 2: Wait for Spark Output (_SUCCESS File)

Spark jobs write a `_SUCCESS` marker when the job completes. Wait for this rather than individual part files.

```python
S3KeySensor(
    task_id="wait_for_spark_output",
    bucket_key="s3://data-lake/processed/{{ ds_nodash }}/_SUCCESS",
    aws_conn_id="aws_default",
    poke_interval=60,
    timeout=2 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 3: Wildcard Pattern (Any Matching File)

```python
# Wait for any Parquet part file to appear
S3KeySensor(
    task_id="wait_for_any_parquet",
    bucket_key="s3://data-lake/output/{{ ds }}/part-*.parquet",
    wildcard_match=True,
    aws_conn_id="aws_default",
    poke_interval=120,
    timeout=3 * 60 * 60,
    mode="reschedule",
)

# Wait for any file in today's prefix
S3KeySensor(
    task_id="wait_for_any_file_today",
    bucket_name="vendor-data-bucket",
    bucket_key="incoming/{{ ds }}/*",
    wildcard_match=True,
    aws_conn_id="vendor_aws_conn",
    poke_interval=300,
    timeout=8 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 4: Multiple Keys (All Must Exist)

```python
S3KeySensor(
    task_id="wait_for_complete_dataset",
    bucket_key=[
        "s3://my-bucket/data/{{ ds }}/sales.parquet",
        "s3://my-bucket/data/{{ ds }}/customers.parquet",
        "s3://my-bucket/data/{{ ds }}/_SUCCESS",
    ],
    aws_conn_id="aws_default",
    poke_interval=60,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 5: Deferrable Mode (Airflow 3 — Recommended)

Consumes no worker slot while waiting. Requires the Airflow Triggerer component.

```python
S3KeySensor(
    task_id="wait_for_file_deferrable",
    bucket_key="s3://vendor-bucket/daily/{{ ds }}/data.csv",
    aws_conn_id="aws_default",
    deferrable=True,         # Use async Triggerer
    poke_interval=60,        # How often Triggerer checks S3
    timeout=8 * 60 * 60,
)
```

---

### Pattern 6: Custom Content Validation with check_fn

```python
def check_file_has_content(objects) -> bool:
    """Ensure the file exists AND is larger than 1KB."""
    for obj in objects:
        size_bytes = obj.get("Size", 0)
        key = obj.get("Key", "unknown")
        print(f"  Key: {key}, Size: {size_bytes} bytes")
        if size_bytes < 1024:  # Less than 1KB
            print("File exists but is too small — might still be uploading")
            return False
    return len(objects) > 0

S3KeySensor(
    task_id="wait_for_valid_file",
    bucket_key="s3://my-bucket/data/{{ ds }}/output.csv",
    aws_conn_id="aws_default",
    check_fn=check_file_has_content,
    poke_interval=60,
    timeout=2 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 7: Optional File with soft_fail

```python
# This enrichment file is optional
S3KeySensor(
    task_id="wait_for_optional_enrichment",
    bucket_key="s3://enrichment-bucket/{{ ds }}/geo_data.csv",
    aws_conn_id="aws_default",
    poke_interval=120,
    timeout=3600,
    mode="reschedule",
    soft_fail=True,   # Skip (not fail) if file doesn't arrive
)

# Downstream task must handle the skipped case
process = PythonOperator(
    task_id="process_data",
    trigger_rule="none_failed",  # Runs even if the sensor was skipped
    python_callable=my_fn,
)
```

---

## Wildcard Pattern Reference

| Pattern | What It Matches |
|---|---|
| `data/{{ ds }}/*.csv` | Any `.csv` in today's date prefix |
| `output/part-*.parquet` | Spark part files |
| `batches/{{ ds }}/_SUCCESS` | Exact sentinel file (no wildcard needed) |
| `reports/{{ ds }}/report_??.xlsx` | Two-digit suffix (e.g., `report_01.xlsx`) |
| `data/*/latest.json` | `latest.json` in any direct subdirectory |

**Performance tip:** Wildcards in the middle of paths (e.g., `data/*/file.csv`) cause S3 to list many keys. Prefer wildcards at the end of paths for better performance.

---

## Sensor Mode Comparison

| Mode | Worker slot | Triggerer needed | Best for |
|---|---|---|---|
| `mode="poke"` | Held | No | Wait < 2 minutes |
| `mode="reschedule"` | Released | No | Wait minutes to hours |
| `deferrable=True` | Not used | Yes | Long waits, many parallel sensors |

**In Airflow 3:** Use `deferrable=True` as the default for all production S3KeySensor usage.

---

## Required IAM Permissions

```json
{
    "Action": [
        "s3:HeadObject",    // Exact key check
        "s3:ListBucket",    // Wildcard / prefix listing
        "s3:GetObject"      // Only if using check_fn to read content
    ],
    "Resource": [
        "arn:aws:s3:::your-bucket",
        "arn:aws:s3:::your-bucket/*"
    ]
}
```

---

## When to Use / Avoid

**Use S3KeySensor when:**
- Waiting for vendor/partner files delivered to S3
- Gating on Spark or EMR job completion (`_SUCCESS` file)
- Waiting for any file matching a naming pattern in a date-partitioned bucket
- Cloud-native data pipelines built on S3 as the data storage layer

**Avoid S3KeySensor when:**
- Files are on local/NFS filesystem — use `FileSensor`
- Files are on SFTP — use `SFTPSensor`
- You need to wait for database records, not files — use `SqlSensor`
- Event-driven S3 triggers are needed — consider AWS EventBridge + Airflow REST API trigger instead

---

## Golden Rules

1. **Always set `timeout`** — default is 7 days. Set a realistic value (4–8 hours for vendor files).
2. **Use `deferrable=True` in Airflow 3** — the most efficient option for long S3 waits.
3. **Use `mode="reschedule"` if not using deferrable** — never block a worker slot for hours.
4. **Use wildcards efficiently** — put wildcards at the end of the path, not in the middle.
5. **Check IAM permissions first** when debugging stuck sensors** — `AccessDenied` is silent in sensor logs.
6. **Use `_SUCCESS` files for job completion** — wait for the sentinel file, not individual part files.
7. **Use Jinja templates in `bucket_key`** — always use `{{ ds }}` or `{{ ds_nodash }}` for date-partitioned paths.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview questions |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [ExternalTaskSensor](../03_ExternalTaskSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [Sensors Overview](../Theory.md)
