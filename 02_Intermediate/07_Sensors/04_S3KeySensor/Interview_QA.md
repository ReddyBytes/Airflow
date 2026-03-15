# S3KeySensor — Interview Q&A

---

## Beginner Questions

### Q1: What is S3KeySensor and what problem does it solve?

**Answer:**

`S3KeySensor` is an Airflow sensor (from the `apache-airflow-providers-amazon` package) that waits for a specific object (key) to appear in an AWS S3 bucket before allowing the pipeline to continue.

**The problem it solves:** Your pipeline needs to process a supplier's data file that gets uploaded to S3 every morning — but you never know exactly when. If you schedule your DAG at 6am and the file arrives at 8am, your run fails. If you schedule at 9am and the file arrived at 6:30am, you wasted 2.5 hours.

`S3KeySensor` starts immediately, checks S3 every few minutes, and triggers the moment the file appears:

```
6:00 AM  — DAG starts, S3KeySensor begins checking
6:05 AM  — File not in S3 yet... waiting
6:10 AM  — Still not there... waiting
6:43 AM  — FILE ARRIVED! Sensor returns True → pipeline continues
```

```python
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

wait_for_delivery = S3KeySensor(
    task_id="wait_for_supplier_file",
    bucket_key="s3://vendor-bucket/daily/{{ ds }}/orders.csv",
    aws_conn_id="aws_default",
    poke_interval=300,
    timeout=8 * 60 * 60,
    mode="reschedule",
)
```

---

### Q2: What is the difference between `bucket_key` and `bucket_name`?

**Answer:**

There are two ways to specify the S3 location:

**Option 1 — Full S3 URI in `bucket_key` (no `bucket_name` needed):**
```python
S3KeySensor(
    bucket_key="s3://my-data-bucket/incoming/{{ ds }}/file.csv",
    # bucket_name not needed — it's part of the URI
)
```

**Option 2 — Key path in `bucket_key` + bucket in `bucket_name`:**
```python
S3KeySensor(
    bucket_name="my-data-bucket",
    bucket_key="incoming/{{ ds }}/file.csv",
    # Full path: s3://my-data-bucket/incoming/2024-01-15/file.csv
)
```

Both approaches work. The full URI form (`s3://bucket/key`) is often clearer. The split form (`bucket_name` + `bucket_key`) is useful when the bucket name is stored in an Airflow Variable or when you're watching multiple keys in the same bucket with a consistent bucket name.

---

### Q3: What is `aws_conn_id` and how do you set it up?

**Answer:**

`aws_conn_id` references an Airflow Connection that holds AWS credentials. The default value is `"aws_default"`.

**Setting up the connection in Airflow UI (Admin → Connections):**

| Field | Value |
|---|---|
| Connection Id | `aws_default` |
| Connection Type | `Amazon Web Services` |
| AWS Access Key ID | Your IAM access key |
| AWS Secret Access Key | Your IAM secret key |
| Extra | `{"region_name": "us-east-1"}` |

**For production on AWS (recommended — use IAM roles instead of keys):**
```bash
# Leave login/password empty; use EC2 instance role or EKS pod identity
airflow connections add 'aws_default' \
  --conn-type 'aws' \
  --conn-extra '{"region_name": "us-east-1"}'
```

In production, avoid hardcoding IAM keys. Use instance profiles, EKS service accounts, or AWS Secrets Manager.

---

### Q4: What does `wildcard_match` do?

**Answer:**

When `wildcard_match=True`, the `bucket_key` is treated as a glob pattern instead of an exact S3 key. The sensor succeeds when **at least one** S3 key matches the pattern.

```python
# Exact key — requires this specific file
S3KeySensor(
    bucket_key="s3://my-bucket/data/2024-01-15/report.csv",
    wildcard_match=False,  # default
)

# Wildcard — succeeds when any matching file exists
S3KeySensor(
    bucket_key="s3://my-bucket/data/{{ ds }}/part-*.parquet",
    wildcard_match=True,
    # Matches: part-000.parquet, part-001.parquet, part-final.parquet, etc.
)
```

Common wildcard patterns:

| Pattern | Matches |
|---|---|
| `data/{{ ds }}/*.csv` | Any `.csv` file in today's prefix |
| `output/part-*.parquet` | Spark part files |
| `reports/{{ ds }}/*` | Any file in today's reports folder |
| `batches/{{ ds }}/_SUCCESS` | Hadoop-style success sentinel file |

---

### Q5: What is the `verify` parameter?

**Answer:**

`verify` controls SSL certificate verification for the S3 connection. It mirrors the `verify` parameter in the `boto3` / `requests` library:

- `verify=True` (default): verifies SSL certificates. Standard and secure.
- `verify=False`: disables SSL verification. Only use in isolated dev/test environments — never in production.
- `verify="/path/to/ca_bundle.crt"`: use a custom CA bundle (for private S3-compatible endpoints).

```python
# Standard S3 with SSL verification (default, production)
S3KeySensor(bucket_key="s3://my-bucket/file.csv", verify=True)

# Private MinIO endpoint with custom certificate
S3KeySensor(
    bucket_key="s3://my-bucket/file.csv",
    aws_conn_id="my_minio_conn",
    verify="/etc/ssl/custom_ca.crt",
)

# Development only — NEVER in production
S3KeySensor(bucket_key="s3://dev-bucket/file.csv", verify=False)
```

---

## Intermediate Questions

### Q6: What is the difference between S3KeySensor and FileSensor?

**Answer:**

Both wait for a file to exist, but they target completely different storage systems:

| Aspect | `FileSensor` | `S3KeySensor` |
|---|---|---|
| Storage | Local or NFS-mounted filesystem | AWS S3 (object storage) |
| Connection type | `fs_conn_id` (File path) | `aws_conn_id` (AWS credentials) |
| Import | `airflow.sensors.filesystem` | `airflow.providers.amazon.aws.sensors.s3` |
| Wildcard support | Python `glob` module | `wildcard_match=True` (S3 prefix listing) |
| Multi-key support | Multiple sensor tasks | Single sensor with `bucket_key=[list]` |
| Deferrable mode | No | Yes (`deferrable=True` in Airflow 3) |
| File metadata | Not available | Can use `check_fn` to validate size/metadata |
| Typical use | On-premises, local files | Cloud data lakes, vendor S3 drops |

**Rule of thumb:** For any file on AWS — use `S3KeySensor`. For files on the Airflow worker's filesystem or an NFS mount — use `FileSensor`.

---

### Q7: How do you wait for multiple S3 keys with a single sensor?

**Answer:**

Pass a **list** to `bucket_key`. The sensor waits until **all keys in the list** exist:

```python
# Wait for all three part files to be present
S3KeySensor(
    task_id="wait_for_all_parts",
    bucket_key=[
        "s3://data-lake/output/{{ ds }}/part-000.parquet",
        "s3://data-lake/output/{{ ds }}/part-001.parquet",
        "s3://data-lake/output/{{ ds }}/_SUCCESS",
    ],
    aws_conn_id="aws_default",
    poke_interval=60,
    timeout=3600,
    mode="reschedule",
)
```

This is more efficient than running three separate sensors, because it makes a single set of S3 API calls per poke cycle rather than three separate poke tasks.

**Note:** When using a key list, `wildcard_match` does not apply — all keys must be exact matches.

---

### Q8: What is poke mode vs reschedule mode vs deferrable mode?

**Answer:**

`S3KeySensor` supports three waiting strategies in Airflow 3:

| Mode | Worker slot usage | How it works | Best for |
|---|---|---|---|
| `mode="poke"` | Held entire time | Worker sleeps in a loop | Very short waits (< 2 min) |
| `mode="reschedule"` | Released between pokes | Worker freed; task rescheduled | Waits of minutes/hours |
| `deferrable=True` | Not used at all | Async Triggerer handles the wait | Long waits (hours), many parallel sensors |

```python
# poke mode (default) — only for very short waits
S3KeySensor(mode="poke", poke_interval=30, ...)

# reschedule mode — production standard for moderate waits
S3KeySensor(mode="reschedule", poke_interval=300, ...)

# deferrable mode — Airflow 3 best practice for long waits
S3KeySensor(deferrable=True, poke_interval=60, ...)
```

**Production recommendation for Airflow 3:** Use `deferrable=True`. It requires the Airflow Triggerer component to be running, but it consumes zero worker slots while waiting.

---

### Q9: What is `prefix` vs `wildcard_match`, and how do they relate to S3 key patterns?

**Answer:**

S3 doesn't have a true directory structure — all objects are identified by their full key (path). When `S3KeySensor` uses `wildcard_match=True`, it performs an S3 `list_objects_v2` call with a computed prefix and then filters matching keys by the glob pattern client-side.

This means:
- Wildcards in the **middle** of a path (e.g., `data/*/orders.csv`) require listing a broad prefix and filtering — this can be slow for large buckets.
- Wildcards at the **end** (e.g., `data/2024-01-15/*.csv`) are more efficient — the prefix is specific.

```python
# Efficient: specific prefix, wildcard only in filename
S3KeySensor(
    bucket_key="s3://my-bucket/data/{{ ds }}/*.parquet",
    wildcard_match=True,   # Lists only keys under data/2024-01-15/
)

# Less efficient: wildcard in middle (lists all keys under data/)
S3KeySensor(
    bucket_key="s3://my-bucket/data/*/orders_{{ ds_nodash }}.csv",
    wildcard_match=True,
)
```

For very large S3 buckets, prefer specific prefixes with wildcards only in the filename portion.

---

## Advanced Questions

### Q10: How does S3KeySensor handle IAM permissions?

**Answer:**

`S3KeySensor` uses the `S3Hook` internally, which calls `s3.list_objects_v2` (for wildcard) or `s3.head_object` (for exact key) via `boto3`. The IAM role/user associated with the `aws_conn_id` connection needs the following minimum permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:HeadObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::my-bucket",
                "arn:aws:s3:::my-bucket/*"
            ]
        }
    ]
}
```

- `s3:HeadObject` — needed for exact key checks
- `s3:ListBucket` — needed for wildcard/prefix matching
- `s3:GetObject` — needed if using `check_fn` to inspect object content

If the sensor keeps timing out on keys you know exist, check CloudTrail logs for `AccessDenied` errors — permissions are a common silent failure.

---

### Q11: What is the `check_fn` parameter (Airflow 3)?

**Answer:**

`check_fn` is a parameter available in newer versions of the Amazon provider that allows custom validation on the found S3 objects. It receives a list of matching S3 key dictionaries and should return `True` if they satisfy your condition.

```python
def check_file_not_empty(objects) -> bool:
    """Succeed only if the file is larger than 0 bytes."""
    for obj in objects:
        size = obj.get("Size", 0)
        print(f"Found key: {obj['Key']} ({size} bytes)")
        if size == 0:
            print("File is empty — waiting for non-empty file")
            return False
    return len(objects) > 0

S3KeySensor(
    task_id="wait_for_non_empty_file",
    bucket_key="s3://my-bucket/data/{{ ds }}/output.csv",
    aws_conn_id="aws_default",
    check_fn=check_file_not_empty,
    poke_interval=120,
    timeout=3600,
    mode="reschedule",
)
```

This is useful when a file may be created as an empty placeholder before actual content is written — you want to wait until the file has actual data.

---

### Q12: How do you use S3KeySensor in an event-driven architecture with Datasets?

**Answer:**

In Airflow 3, `S3KeySensor` can be combined with Dataset-aware scheduling for a fully event-driven pattern. However, for true event-driven S3 triggers, the most efficient approach is using **deferrable S3KeySensor** with Dataset outlets:

```python
from airflow import Dataset
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.operators.python import PythonOperator

# Define a dataset representing the S3 file
vendor_orders_dataset = Dataset("s3://vendor-bucket/orders/{{ ds }}/orders.csv")

with DAG(
    dag_id="wait_and_trigger_pipeline",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    # Deferrable sensor — no worker slot consumed while waiting
    wait_for_file = S3KeySensor(
        task_id="wait_for_vendor_orders",
        bucket_key="s3://vendor-bucket/orders/{{ ds }}/orders.csv",
        aws_conn_id="aws_default",
        deferrable=True,
        poke_interval=60,
        timeout=8 * 60 * 60,
    )

    def mark_data_available(**context):
        print(f"Vendor orders file confirmed in S3 for {context['ds']}")

    confirm = PythonOperator(
        task_id="confirm_availability",
        python_callable=mark_data_available,
        outlets=[vendor_orders_dataset],   # Triggers any DAG that depends on this dataset
    )

    wait_for_file >> confirm
```

Any DAG with `schedule=[vendor_orders_dataset]` will automatically be triggered when this pipeline confirms the file, creating a clean event-driven dependency chain.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [ExternalTaskSensor](../03_ExternalTaskSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [Sensors Overview](../Theory.md)
