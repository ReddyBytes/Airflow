# Event-Driven Scheduling — Cheatsheet

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**

---

## Core Concepts at a Glance

| Concept | What it is | Import |
|---------|-----------|--------|
| `Asset` | Named reference to a data artifact, identified by URI | `from airflow.sdk import Asset` |
| `outlets` | Task parameter — marks assets as updated when task succeeds | `@task(outlets=[my_asset])` |
| `schedule=[asset]` | DAG runs when all listed assets are updated | `with DAG(..., schedule=[asset])` |
| `AssetAll` | Explicit AND — all assets must update (same as list) | `from airflow.sdk import AssetAll` |
| `AssetAny` | OR — any one asset triggers the DAG | `from airflow.sdk import AssetAny` |
| `AssetAlias` | Stable name pointing to any underlying asset | `from airflow.sdk import AssetAlias` |
| `@asset` decorator | Creates an asset + its producing DAG in one declaration | `from airflow.sdk import asset` |

---

## Asset URI Patterns

```python
from airflow.sdk import Asset

# S3 object
sales_file    = Asset("s3://my-bucket/data/sales.parquet")

# GCS object
reports_file  = Asset("gs://my-bucket/reports/monthly.csv")

# Database table (logical reference — Airflow does not check the table exists)
orders_table  = Asset("postgres://myhost/mydb/orders")

# Custom logical name (any valid URI works)
ml_model      = Asset("model://fraud-detection/v3")

# Local file
raw_data      = Asset("file:///opt/airflow/data/raw.json")
```

The URI is the identity. Two `Asset("s3://...")` with the same URI are the same asset.

---

## Defining an Asset (Simple)

```python
from airflow.sdk import Asset

# Define once — import this wherever you need to reference the asset
DAILY_SALES = Asset("s3://data-lake/sales/daily/sales.parquet")
```

---

## Producer DAG — Marking an Asset as Updated

```python
from airflow.sdk import DAG, Asset
from airflow.decorators import task
from datetime import datetime

DAILY_SALES = Asset("s3://data-lake/sales/daily/sales.parquet")

with DAG(
    dag_id="ingest_sales",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    @task(outlets=[DAILY_SALES])    # <-- marks asset as updated on success
    def extract_and_upload():
        # write file to S3
        print("Uploading sales.parquet to S3...")

    extract_and_upload()
```

---

## Consumer DAG — Triggered by an Asset

```python
from airflow.sdk import DAG, Asset
from airflow.decorators import task
from datetime import datetime

DAILY_SALES = Asset("s3://data-lake/sales/daily/sales.parquet")

with DAG(
    dag_id="transform_sales",
    schedule=[DAILY_SALES],         # <-- runs whenever DAILY_SALES is updated
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    @task
    def transform():
        print("Transforming sales data...")

    transform()
```

---

## Multiple Asset Dependencies (AND Logic)

```python
# All three assets must be updated before this DAG runs
from airflow.sdk import DAG, Asset, AssetAll

SALES   = Asset("s3://data/sales.parquet")
RETURNS = Asset("s3://data/returns.parquet")
COSTS   = Asset("s3://data/costs.parquet")

with DAG(
    dag_id="build_p_and_l",
    schedule=[SALES, RETURNS, COSTS],   # AND — all three must update
    # Equivalent: schedule=AssetAll(SALES, RETURNS, COSTS)
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

---

## OR Logic — Any Asset Triggers the DAG

```python
from airflow.sdk import AssetAny

# Trigger when EITHER the sales file OR the emergency override is updated
with DAG(
    dag_id="flexible_report",
    schedule=AssetAny(DAILY_SALES, EMERGENCY_OVERRIDE),
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

---

## Complex Conditions

```python
from airflow.sdk import AssetAny, AssetAll

# Trigger when: (sales AND returns are both updated) OR (override is updated alone)
with DAG(
    dag_id="smart_report",
    schedule=AssetAny(
        AssetAll(SALES, RETURNS),
        EMERGENCY_OVERRIDE,
    ),
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

---

## Asset + Time Schedule Combo

```python
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

# Run when the asset is updated, OR at 06:00 UTC daily (whichever comes first)
with DAG(
    dag_id="daily_or_on_data",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 6 * * *", timezone="UTC"),
        assets=[DAILY_SALES],
    ),
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

---

## The @asset Decorator (Producer + Asset in One)

```python
from airflow.sdk import asset
from datetime import datetime

# This creates both:
#   1. An Asset("s3://data-lake/sales/daily/sales.parquet")
#   2. A DAG "daily_sales_producer" with a single task

@asset(
    uri="s3://data-lake/sales/daily/sales.parquet",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
)
def daily_sales_producer():
    """Produces the daily sales file. Any DAG scheduling on this asset
    will be triggered when this function completes successfully."""
    print("Writing sales.parquet to S3...")
```

Consume it by referencing the function name:

```python
with DAG(
    dag_id="consume_sales",
    schedule=[daily_sales_producer],   # reference the decorated function
    start_date=datetime(2026, 1, 1),
) as dag:
    ...
```

---

## Chaining Asset-Dependent DAGs

```
ingest_sales (schedule: @daily)
    └── [DAILY_SALES asset updated]
            └── transform_sales (schedule: [DAILY_SALES])
                    └── [MONTHLY_REPORT asset updated]
                            └── send_report (schedule: [MONTHLY_REPORT])
```

```python
from airflow.sdk import DAG, Asset
from airflow.decorators import task
from datetime import datetime

DAILY_SALES    = Asset("s3://data/sales.parquet")
MONTHLY_REPORT = Asset("s3://reports/monthly.parquet")

# DAG 1 — produces DAILY_SALES
with DAG("ingest_sales", schedule="@daily", start_date=datetime(2026, 1, 1)) as dag1:
    @task(outlets=[DAILY_SALES])
    def ingest(): pass
    ingest()

# DAG 2 — consumes DAILY_SALES, produces MONTHLY_REPORT
with DAG("transform_sales", schedule=[DAILY_SALES], start_date=datetime(2026, 1, 1)) as dag2:
    @task(outlets=[MONTHLY_REPORT])
    def transform(): pass
    transform()

# DAG 3 — consumes MONTHLY_REPORT
with DAG("send_report", schedule=[MONTHLY_REPORT], start_date=datetime(2026, 1, 1)) as dag3:
    @task
    def send(): pass
    send()
```

---

## Accessing Asset Event Context in Consumer Tasks

```python
@task
def process(**context):
    events = context.get("triggering_asset_events", {})
    for uri, asset_events in events.items():
        for e in asset_events:
            print(f"Triggered by: {uri}")
            print(f"  Source DAG:  {e.source_dag_id}")
            print(f"  Source run:  {e.source_run_id}")
            print(f"  Updated at:  {e.timestamp}")
```

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Different URI strings for same asset | Use a shared module: `from shared.assets import MY_ASSET` |
| Expecting consumer to run when producer has NO `outlets` | Add `outlets=[asset]` to the producing task |
| Consumer never triggers | Check that the producer task actually *succeeded* (failed tasks do not update assets) |
| `AssetNotFound` error | The asset must have been updated at least once before the consumer triggers |

---

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**
