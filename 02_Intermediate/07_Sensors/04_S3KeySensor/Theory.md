# S3KeySensor in Apache Airflow 3

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Code Examples](./Code_Example.md)**

---

## The Story: Waiting for a File That Hasn't Arrived Yet

Your pipeline processes supplier data files uploaded to an S3 bucket every morning. The problem: the supplier uploads sometime between 6 AM and 10 AM, and you never know exactly when. If you schedule your DAG at 6 AM, it will fail most days because the file isn't there yet. If you schedule at 10 AM, you are wasting 4 hours when the file often arrives at 6:30 AM.

`S3KeySensor` solves this elegantly. It wakes up every few minutes, checks whether the file exists in S3, and either waits or proceeds — automatically. Your pipeline starts processing the moment the file appears, not at an arbitrary scheduled time.

```
6:00 AM  — DAG starts, S3KeySensor begins checking
6:05 AM  — File not there yet... checking again in 5 minutes
6:10 AM  — File not there yet... checking again
6:43 AM  — FILE ARRIVED! Sensor returns True, pipeline continues
```

No manual intervention. No failed runs. No wasted waiting.

---

## What Is S3KeySensor?

`S3KeySensor` (from `apache-airflow-providers-amazon`) is a sensor that polls an S3 bucket at a configured interval until a specified key (file path) exists. It can match exact paths or wildcard patterns. It supports both traditional (blocking) mode and modern deferrable (async) mode.

---

## Setup

```bash
pip install apache-airflow-providers-amazon
```

### Create an AWS Connection in Airflow

**Via UI (Admin → Connections):**
- Connection ID: `aws_default`
- Connection Type: `Amazon Web Services`
- AWS Access Key ID: your key
- AWS Secret Access Key: your secret
- Extra: `{"region_name": "us-east-1"}`

**Via CLI:**
```bash
airflow connections add 'aws_default' \
  --conn-type 'aws' \
  --conn-login 'AKIAIOSFODNN7EXAMPLE' \
  --conn-password 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' \
  --conn-extra '{"region_name": "us-east-1"}'
```

**With IAM Role (recommended for production on AWS):**
```bash
# Leave login/password empty — use EC2 instance role or EKS pod identity
airflow connections add 'aws_default' \
  --conn-type 'aws' \
  --conn-extra '{"region_name": "us-east-1"}'
```

---

## Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `bucket_key` | `str \| list[str]` | required | S3 key (path) to check. Can include wildcards. Supports Jinja. |
| `bucket_name` | `str` | `None` | S3 bucket name. If included in `bucket_key` as `s3://bucket/key`, not needed separately. |
| `aws_conn_id` | `str` | `"aws_default"` | Airflow Connection for AWS credentials |
| `wildcard_match` | `bool` | `False` | If `True`, treat `bucket_key` as a glob pattern |
| `poke_interval` | `float` | `60.0` | Seconds between checks (in non-deferrable mode) |
| `timeout` | `float` | `604800` | Max seconds to wait before failing (default: 7 days) |
| `mode` | `str` | `"poke"` | `"poke"` (blocking) or `"reschedule"` (frees worker slot) |
| `deferrable` | `bool` | `False` | Use async trigger — highly efficient for long waits |
| `verify` | `bool \| str` | `None` | SSL verification |
| `use_glob` | `bool` | `False` | Use glob matching (superseded by `wildcard_match`) |
| `check_fn` | `Callable` | `None` | Optional function to perform additional validation on found keys |

---

## Sensor Modes Explained

### Mode 1: `poke` (default — blocking)

The sensor runs in a loop inside its assigned worker slot. The worker is blocked for the entire wait duration. Use this when you expect the file to arrive quickly (within minutes).

```python
S3KeySensor(
    task_id="wait_for_file",
    mode="poke",
    poke_interval=60,  # Check every 60 seconds
    timeout=3600,      # Give up after 1 hour
    ...
)
```

### Mode 2: `reschedule` (frees worker)

The sensor checks, then releases its worker slot, and Airflow reschedules it later. The worker is available for other tasks between checks. Better for long waits in environments with limited worker slots.

```python
S3KeySensor(
    task_id="wait_for_file",
    mode="reschedule",
    poke_interval=300,   # Check every 5 minutes
    timeout=86400,       # Give up after 24 hours
    ...
)
```

### Mode 3: `deferrable=True` (async — recommended in Airflow 3)

The sensor uses Airflow's async trigger infrastructure. No worker slot is consumed while waiting. The trigger runs in the triggerer process and wakes up the task when the key appears. Highly efficient for long waits.

```python
S3KeySensor(
    task_id="wait_for_file",
    deferrable=True,
    poke_interval=60,     # How often the async trigger checks S3
    timeout=86400,
    ...
)
```

---

## Mermaid: S3KeySensor Decision Flow

```mermaid
flowchart TD
    A([DAG run starts]) --> B[S3KeySensor wakes up]
    B --> C{Check S3: does key exist?}
    C -->|No| D{Mode?}
    D -->|poke| E[Sleep poke_interval seconds]
    D -->|reschedule| F[Release worker slot, reschedule]
    D -->|deferrable| G[Defer to async triggerer]
    E --> C
    F --> C
    G --> C
    C -->|Yes| H{wildcard_match?}
    H -->|False| I{Exact key found?}
    H -->|True| J{Any key matches pattern?}
    I -->|Yes| K([Sensor succeeds — pipeline continues])
    I -->|No| C
    J -->|Yes| K
    J -->|No| C
    C -->|Timeout exceeded| L([Sensor fails])

    style A fill:#4a90d9,color:#fff
    style K fill:#27ae60,color:#fff
    style L fill:#e74c3c,color:#fff
    style G fill:#9b59b6,color:#fff
```

---

## `bucket_key` Format Options

```python
# Option 1: Full S3 URI (bucket_name not needed)
bucket_key="s3://my-bucket/data/2025-03-15/sales.csv"

# Option 2: Key only (bucket_name required)
bucket_name="my-bucket"
bucket_key="data/2025-03-15/sales.csv"

# Option 3: With Jinja templating
bucket_key="s3://my-bucket/data/{{ ds }}/sales.csv"

# Option 4: Wildcard pattern (wildcard_match=True required)
bucket_key="s3://my-bucket/data/2025-03-15/*.parquet"

# Option 5: Multiple keys (all must exist before sensor returns)
bucket_key=[
    "s3://my-bucket/data/{{ ds }}/part-000.parquet",
    "s3://my-bucket/data/{{ ds }}/part-001.parquet",
    "s3://my-bucket/data/{{ ds }}/_SUCCESS",
]
```

---

## Wildcard Matching

When `wildcard_match=True`, the `bucket_key` is treated as a glob pattern. The sensor succeeds when at least one matching key is found.

| Pattern | Matches |
|---|---|
| `data/2025-03-15/*.csv` | Any `.csv` in that prefix |
| `data/2025-03-15/part-*.parquet` | Any Parquet file starting with `part-` |
| `data/*/sales.csv` | `sales.csv` in any subdirectory |
| `data/2025-03-??/*.json` | Any `.json` in any day of March 2025 |

---

## Common Patterns

### Pattern 1: Wait for a Daily Delivery File

```python
S3KeySensor(
    task_id="wait_for_daily_delivery",
    bucket_key="s3://vendor-bucket/daily/{{ ds }}/delivery.csv",
    aws_conn_id="vendor_s3",
    poke_interval=300,    # Check every 5 minutes
    timeout=28800,        # Give up after 8 hours
    mode="reschedule",
    deferrable=True,
)
```

### Pattern 2: Wait for Spark Job Output (`_SUCCESS` file)

```python
S3KeySensor(
    task_id="wait_for_spark_output",
    bucket_key="s3://data-lake/processed/{{ ds_nodash }}/_SUCCESS",
    aws_conn_id="aws_default",
    poke_interval=60,
    timeout=3600,
    deferrable=True,
)
```

### Pattern 3: Wait for Any Part File (Wildcard)

```python
S3KeySensor(
    task_id="wait_for_any_part",
    bucket_key="data/{{ ds }}/part-*.parquet",
    bucket_name="data-lake-bucket",
    wildcard_match=True,
    aws_conn_id="aws_default",
    poke_interval=120,
    timeout=7200,
    deferrable=True,
)
```

---

## Key Takeaways

- `S3KeySensor` polls S3 for a file or wildcard match before allowing the pipeline to proceed.
- Use `mode="reschedule"` or `deferrable=True` in production to free worker slots during long waits.
- `bucket_key` supports Jinja templating — use `{{ ds }}` or `{{ ds_nodash }}` for date-based paths.
- `wildcard_match=True` lets you wait for "any file matching this pattern" rather than an exact key.
- Always set a `timeout` to avoid sensors running indefinitely if the file never arrives.
- `deferrable=True` is the most efficient mode in Airflow 3 — it uses no worker slot while waiting.
