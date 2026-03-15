# Asset-Driven Scheduling — Cheatsheet

## Navigation
⬅️ **Prev: [What's New in Airflow 3](../30_Whats_New_in_Airflow_3/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Versioning](../32_DAG_Versioning/Theory.md)**

---

## Asset Definition Syntax

```python
from airflow.sdk import Asset, AssetAlias

# Minimal
asset = Asset("s3://bucket/path/file.parquet")

# Full
asset = Asset(
    uri="s3://bucket/path/file.parquet",
    name="my_asset",          # human-readable name
    group="team_name",        # logical grouping
    extra={"key": "value"},   # arbitrary metadata dict
)

# Alias
alias = AssetAlias("latest_sales")
```

---

## Producer Pattern

```python
from airflow.sdk import Asset
from airflow.decorators import task

my_asset = Asset("s3://bucket/output.parquet")

# In a DAG — mark task as producing an asset
@task(outlets=[my_asset])
def produce_data():
    # write data
    pass

# Multiple outlets
@task(outlets=[asset_a, asset_b])
def produce_multiple():
    pass
```

---

## Consumer Pattern

```python
from airflow.sdk import Asset
from airflow import DAG

my_asset = Asset("s3://bucket/output.parquet")

# schedule= with a list triggers on asset update
with DAG(
    dag_id="consumer",
    schedule=[my_asset],    # triggers when my_asset is updated
    start_date=datetime(2024, 1, 1),
) as dag:
    ...
```

---

## Schedule Parameter Options

| Pattern | Syntax | Trigger Logic |
|---------|--------|---------------|
| Single asset | `schedule=[asset_a]` | When asset_a is updated |
| All assets (AND) | `schedule=[asset_a, asset_b]` | When BOTH updated |
| All assets (AND explicit) | `schedule=AssetAll(asset_a, asset_b)` | When BOTH updated |
| Any asset (OR) | `schedule=AssetAny(asset_a, asset_b)` | When EITHER updated |
| Complex | `schedule=AssetAny(AssetAll(a, b), c)` | When (a AND b) OR c |
| Time-based | `schedule="@daily"` | Normal cron/preset |
| No schedule | `schedule=None` | Manual trigger only |

---

## @asset Decorator Syntax

```python
from airflow.sdk import asset
from datetime import datetime

@asset(
    uri="s3://bucket/output.parquet",   # asset URI
    schedule="@daily",                   # how often to run
    start_date=datetime(2024, 1, 1),
)
def my_producing_function():
    # This function IS the producing task
    pass

# my_producing_function is now an Asset reference
# Use it in a consumer DAG's schedule:
with DAG("consumer", schedule=[my_producing_function]) as dag:
    ...
```

---

## Asset URI Formats

| Backend | URI Pattern | Example |
|---------|------------|---------|
| S3 | `s3://bucket/path/key` | `s3://datalake/orders/2024.parquet` |
| GCS | `gs://bucket/path/object` | `gs://my-bucket/reports/daily.csv` |
| Azure Blob | `abfs://container/path` | `abfs://data/sales/output.json` |
| PostgreSQL | `postgres://host/db/schema/table` | `postgres://warehouse/public/orders` |
| Local file | `file:///path/to/file` | `file:///tmp/output.csv` |
| Custom | Any URI string | `my-system://resource/id` |

---

## Imports Reference

```python
# All Asset-related imports in v3
from airflow.sdk import Asset
from airflow.sdk import AssetAlias
from airflow.sdk import AssetAny
from airflow.sdk import AssetAll
from airflow.sdk import asset       # @asset decorator
```

---

## v2 Dataset → v3 Asset Migration

```python
# v2
from airflow.datasets import Dataset
my_ds = Dataset("s3://bucket/file.csv")

# v3
from airflow.sdk import Asset
my_asset = Asset("s3://bucket/file.csv")  # same URI, new class name
```

---

## Common Patterns

```python
# Shared asset definitions (recommended)
# dags/assets.py
from airflow.sdk import Asset
ORDERS = Asset("s3://data/orders.parquet")
CUSTOMERS = Asset("s3://data/customers.parquet")

# Producer DAG
from assets import ORDERS
@task(outlets=[ORDERS])
def write_orders(): pass

# Consumer DAG
from assets import ORDERS, CUSTOMERS
with DAG("report", schedule=[ORDERS, CUSTOMERS]) as dag: ...
```

---

## Navigation
⬅️ **Prev: [What's New in Airflow 3](../30_Whats_New_in_Airflow_3/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [DAG Versioning](../32_DAG_Versioning/Theory.md)**
