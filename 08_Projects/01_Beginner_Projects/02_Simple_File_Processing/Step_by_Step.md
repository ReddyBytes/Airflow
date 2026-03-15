# Simple File Processing Pipeline — Step by Step Guide

In this project you will build a DAG that watches a folder for CSV files, validates
and transforms them, writes the output to a `processed/` folder, and archives the
original. By the end you will understand `FileSensor`, `PythonOperator`, and how
Airflow handles local file system workflows.

---

## What You Will Build

```
data/
├── input/
│   └── orders_2024-01-15.csv     ← files land here
├── processed/
│   └── orders_2024-01-15.csv     ← clean output written here
└── archive/
    └── orders_2024-01-15.csv     ← original moved here after processing
```

---

## Prerequisites

- Airflow running locally (Docker Compose or `astro dev start`)
- Python 3.11
- `pandas` installed in the Airflow environment

---

## Step 1 — Set Up the Folder Structure

Create the directories that the DAG will use:

```bash
mkdir -p ~/airflow/data/{input,processed,archive}
```

Add this to your `docker-compose.yml` (or Astro project) to mount the data folder
into the Airflow containers:

```yaml
volumes:
  - ~/airflow/data:/opt/airflow/data
```

Verify inside the container:
```bash
docker exec -it airflow-scheduler bash -c "ls /opt/airflow/data"
# Expected: archive  input  processed
```

---

## Step 2 — Create a Sample Input File

```bash
cat > ~/airflow/data/input/orders_2024-01-15.csv << 'EOF'
order_id,customer_id,amount,currency,order_date,status
ORD-00000001,CUST-001,99.99,USD,2024-01-15,shipped
ORD-00000002,CUST-002,249.00,EUR,15/01/2024,pending
ORD-00000003,CUST-003,-10.00,GBP,2024-01-15,cancelled
ORD-00000004,CUST-004,50.00,USD,2024-01-15,delivered
ORD-00000005,,75.00,USD,2024-01-15,shipped
EOF
```

Notice the data quality issues:
- Row 2: date format is `DD/MM/YYYY` instead of `YYYY-MM-DD`
- Row 3: negative amount
- Row 5: missing `customer_id`

The DAG will clean these up.

---

## Step 3 — Create the DAG File

Create `/opt/airflow/dags/file_processing_pipeline.py`:

```python
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import shutil

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.filesystem import FileSensor

BASE_DIR = Path("/opt/airflow/data")
INPUT_DIR = BASE_DIR / "input"
PROCESSED_DIR = BASE_DIR / "processed"
ARCHIVE_DIR = BASE_DIR / "archive"

# Ensure directories exist when the DAG is loaded
for d in [INPUT_DIR, PROCESSED_DIR, ARCHIVE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def find_input_file(**context):
    """Find the CSV file matching today's date in the input directory."""
    logical_date = context["ds"]                    # e.g. "2024-01-15"
    pattern = f"orders_{logical_date}.csv"
    matches = list(INPUT_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern} in {INPUT_DIR}")
    file_path = str(matches[0])
    context["ti"].xcom_push(key="input_file", value=file_path)
    print(f"Found input file: {file_path}")


def validate_and_transform(**context):
    """Read CSV, validate, clean, and write to processed directory."""
    file_path = context["ti"].xcom_pull(key="input_file", task_ids="find_file")
    df = pd.read_csv(file_path)

    original_count = len(df)
    print(f"Loaded {original_count} rows from {file_path}")

    # --- Validation: drop rows missing critical fields ---
    df = df.dropna(subset=["order_id", "customer_id"])
    print(f"After dropping null key fields: {len(df)} rows")

    # --- Validation: drop rows with negative amounts ---
    df = df[df["amount"] >= 0]
    print(f"After dropping negative amounts: {len(df)} rows")

    # --- Transformation: normalise date format ---
    df["order_date"] = pd.to_datetime(df["order_date"], dayfirst=False, errors="coerce")
    df = df.dropna(subset=["order_date"])          # drop rows with unparseable dates
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d")

    # --- Transformation: uppercase column names ---
    df.columns = [c.upper() for c in df.columns]

    # --- Transformation: add processing metadata ---
    df["PROCESSED_AT"] = datetime.utcnow().isoformat()
    df["SOURCE_FILE"] = Path(file_path).name

    output_path = PROCESSED_DIR / Path(file_path).name
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} clean rows to {output_path}")

    context["ti"].xcom_push(key="output_file", value=str(output_path))
    context["ti"].xcom_push(key="row_count", value=len(df))


def archive_original(**context):
    """Move the original file to the archive directory."""
    input_file = context["ti"].xcom_pull(key="input_file", task_ids="find_file")
    dest = ARCHIVE_DIR / Path(input_file).name
    shutil.move(input_file, dest)
    print(f"Archived {input_file} → {dest}")


def print_summary(**context):
    """Print a run summary."""
    output_file = context["ti"].xcom_pull(key="output_file", task_ids="transform")
    row_count = context["ti"].xcom_pull(key="row_count", task_ids="transform")
    print("=" * 50)
    print(f"Pipeline complete for {context['ds']}")
    print(f"Output file : {output_file}")
    print(f"Clean rows  : {row_count}")
    print("=" * 50)


with DAG(
    dag_id="simple_file_processing",
    start_date=datetime(2024, 1, 15),
    schedule="@daily",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["beginner", "file-processing"],
    description="Watch input folder → validate → transform → archive CSV files",
) as dag:

    wait_for_file = FileSensor(
        task_id="wait_for_file",
        filepath=str(INPUT_DIR / "orders_{{ ds }}.csv"),
        fs_conn_id="fs_default",
        poke_interval=30,                   # check every 30 seconds
        timeout=600,                        # fail after 10 minutes
        mode="poke",
    )

    find_file = PythonOperator(
        task_id="find_file",
        python_callable=find_input_file,
    )

    transform = PythonOperator(
        task_id="transform",
        python_callable=validate_and_transform,
    )

    archive = PythonOperator(
        task_id="archive_original",
        python_callable=archive_original,
    )

    summarise = PythonOperator(
        task_id="print_summary",
        python_callable=print_summary,
    )

    wait_for_file >> find_file >> transform >> archive >> summarise
```

---

## Step 4 — Configure the FileSensor Connection

The `FileSensor` needs a filesystem connection:

1. Open Airflow UI → **Admin → Connections → +**
2. Fill in:
   - **Conn ID**: `fs_default`
   - **Conn Type**: `File (path)`
   - **Extra**: `{"path": "/"}`
3. Save.

Alternatively, set it via environment variable:
```bash
export AIRFLOW_CONN_FS_DEFAULT='{"conn_type": "fs", "extra": {"path": "/"}}'
```

---

## Step 5 — Trigger and Observe

```bash
# Trigger for a specific date
airflow dags trigger simple_file_processing --conf '{}' --exec-date 2024-01-15

# Watch the task states
airflow tasks states-for-dag-run simple_file_processing <run_id>
```

Expected task sequence:
```
wait_for_file → success (file found)
find_file     → success
transform     → success
archive_original → success
print_summary → success
```

---

## Expected Output

After a successful run:

```bash
ls ~/airflow/data/processed/
# orders_2024-01-15.csv

cat ~/airflow/data/processed/orders_2024-01-15.csv
# ORDER_ID,CUSTOMER_ID,AMOUNT,CURRENCY,ORDER_DATE,STATUS,PROCESSED_AT,SOURCE_FILE
# ORD-00000001,CUST-001,99.99,USD,2024-01-15,shipped,2024-01-15T10:23:01,...
# ORD-00000004,CUST-004,50.00,USD,2024-01-15,delivered,...

ls ~/airflow/data/archive/
# orders_2024-01-15.csv   (original moved here)

ls ~/airflow/data/input/
# (empty — file was archived)
```

3 rows from the original 5 survive validation (row 3 dropped for negative amount,
row 5 dropped for missing customer_id). Row 2's date is normalised from
`15/01/2024` to `2024-01-15`.

---

## Step 6 — What to Try Next

- Add an `EmailOperator` as a callback when validation drops more than 20 % of rows.
- Swap `PythonOperator` for a `BranchPythonOperator` that sends the file to a
  quarantine folder if all rows fail validation.
- Process multiple files at once using dynamic task mapping.
- Write the output to S3 instead of a local folder.

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Code Example** | [Code_Example.md](./Code_Example.md) |
| **Parent: Beginner Projects** | [01_Beginner_Projects](../Readme.md) |
| **Next Project: Forex ETL** | [01_Forex_ETL_Pipeline](../01_Forex_ETL_Pipeline/) |
