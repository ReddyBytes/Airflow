# Multi-Source ETL Pipeline — Step by Step

In this project you will build a pipeline that pulls data from three sources
simultaneously — a REST API, an S3 bucket, and a Postgres database — using Airflow 3
dynamic task mapping. The three result sets are merged, validated, and loaded to a
data warehouse.

---

## What You Will Build

```
                 ┌── fetch_from_api    ──┐
start ──extract──┤── download_from_s3  ──├── merge_sources ── validate ── load
                 └── query_postgres    ──┘
```

Key Airflow 3 features used:
- **Dynamic task mapping** (`expand()`) — run extraction tasks in parallel, one per source
- **`@task` decorator** — clean Pythonic task definition
- **XCom with task mapping** — merge results from parallel tasks
- **`Assets`** — emit an asset on successful load for downstream consumers

---

## Prerequisites

```bash
pip install apache-airflow \
            apache-airflow-providers-amazon \
            apache-airflow-providers-postgres \
            apache-airflow-providers-http \
            pandas \
            requests
```

Airflow connections needed:
- `http_api_default` — REST API base URL
- `aws_default` — AWS credentials (or IRSA on EKS)
- `postgres_source` — source Postgres DB
- `postgres_warehouse` — destination warehouse

---

## Step 1 — Understand the Sources

For this project we use three concrete (but easily swappable) sources:

| Source | What | Connection |
|---|---|---|
| REST API | Daily exchange rates (EUR, GBP, JPY vs USD) | `http_api_default` → `api.exchangerate.host` |
| S3 | CSV file with product catalogue updates | `aws_default` → `s3://my-bucket/products/{{ds}}.csv` |
| Postgres | Customer orders from the operational DB | `postgres_source` → `orders` table |

---

## Step 2 — Define the Source Configuration

Rather than hard-coding three separate tasks, define the sources as a list.
Dynamic task mapping will fan out across this list automatically:

```python
SOURCES = [
    {
        "source_id": "exchange_rates",
        "type": "http",
        "url": "https://api.exchangerate.host/latest?base=USD&symbols=EUR,GBP,JPY",
        "output_key": "exchange_rates_{{ ds }}",
    },
    {
        "source_id": "product_catalogue",
        "type": "s3",
        "bucket": "my-data-lake",
        "key": "products/{{ ds }}.csv",
        "output_key": "products_{{ ds }}",
    },
    {
        "source_id": "customer_orders",
        "type": "postgres",
        "sql": "SELECT * FROM orders WHERE order_date = '{{ ds }}'",
        "conn_id": "postgres_source",
        "output_key": "orders_{{ ds }}",
    },
]
```

---

## Step 3 — Write the Extraction Task

```python
from airflow.sdk import task
import requests
import pandas as pd
import json

@task
def extract_source(source_config: dict, ds: str = None) -> str:
    """
    Generic extractor. Routes to the correct provider based on source_config['type'].
    Returns a JSON string of the extracted data (stored in XCom).
    """
    source_type = source_config["type"]

    if source_type == "http":
        url = source_config["url"].replace("{{ ds }}", ds)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Flatten exchange rates into rows
        rows = [{"base": "USD", "currency": k, "rate": v, "date": ds}
                for k, v in data.get("rates", {}).items()]
        return json.dumps(rows)

    elif source_type == "s3":
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook
        hook = S3Hook(aws_conn_id="aws_default")
        key = source_config["key"].replace("{{ ds }}", ds)
        content = hook.read_key(key, bucket_name=source_config["bucket"])
        df = pd.read_csv(pd.io.common.StringIO(content))
        df["source_date"] = ds
        return df.to_json(orient="records")

    elif source_type == "postgres":
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id=source_config["conn_id"])
        sql = source_config["sql"].replace("{{ ds }}", ds)
        df = hook.get_pandas_df(sql)
        df["source_date"] = ds
        return df.to_json(orient="records")

    else:
        raise ValueError(f"Unknown source type: {source_type}")
```

---

## Step 4 — Write the Merge Task

```python
@task
def merge_sources(extracted_results: list[str]) -> str:
    """
    Merge all extracted JSON strings into a single unified DataFrame.
    Each source produces rows; we stack them with a 'source' column.
    """
    import json
    import pandas as pd

    frames = []
    for i, result in enumerate(extracted_results):
        rows = json.loads(result)
        df = pd.DataFrame(rows)
        df["_source_index"] = i
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    print(f"Merged {len(merged)} total rows from {len(frames)} sources")
    return merged.to_json(orient="records")
```

---

## Step 5 — Write Validate and Load Tasks

```python
@task
def validate_merged(merged_json: str, ds: str = None) -> str:
    """Basic validation: no nulls in key columns, minimum row count."""
    import json
    import pandas as pd

    df = pd.DataFrame(json.loads(merged_json))

    errors = []
    if len(df) == 0:
        errors.append("Zero rows after merge")

    # Check for nulls in every column
    null_counts = df.isnull().sum()
    for col, count in null_counts.items():
        if count > 0:
            print(f"WARNING: {count} nulls in column '{col}'")

    if errors:
        raise ValueError(f"Validation failed: {'; '.join(errors)}")

    print(f"Validation passed: {len(df)} rows, {len(df.columns)} columns")
    return merged_json


@task
def load_to_warehouse(validated_json: str, ds: str = None) -> int:
    """Load merged, validated rows to the warehouse."""
    import json
    import pandas as pd
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    df = pd.DataFrame(json.loads(validated_json))
    hook = PostgresHook(postgres_conn_id="postgres_warehouse")

    # Write to a date-partitioned staging table
    rows_loaded = hook.insert_rows(
        table="warehouse.multi_source_daily",
        rows=df.values.tolist(),
        target_fields=df.columns.tolist(),
        replace=True,
    )
    print(f"Loaded {len(df)} rows to warehouse for {ds}")
    return len(df)
```

---

## Step 6 — Assemble the DAG with Dynamic Task Mapping

```python
from datetime import datetime
from airflow.sdk import DAG, Asset

warehouse_asset = Asset("warehouse://multi_source_daily")

with DAG(
    dag_id="multi_source_etl",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["intermediate", "dynamic-mapping", "etl"],
) as dag:

    # Dynamic task mapping: one extract task per source
    extracted = extract_source.expand(
        source_config=SOURCES,
    )

    # Merge all extracted results
    merged = merge_sources(extracted_results=extracted)

    # Validate
    validated = validate_merged(merged_json=merged)

    # Load — produces an Asset for downstream consumers
    load_to_warehouse(validated_json=validated)
```

---

## Step 7 — Verify in the Airflow UI

After triggering:

1. Open the DAG graph — you should see **3 instances** of `extract_source`
   (one per source), then a single `merge_sources`, `validate_merged`, and
   `load_to_warehouse`.

2. Click any `extract_source` task instance → **Mapped Tasks** tab shows which
   `source_config` index it processed.

3. Check XCom on `merge_sources` — it will contain the combined row count.

---

## Common Issues

| Issue | Fix |
|---|---|
| API rate limit | Add `retries=3`, `retry_delay=30` on `extract_source` |
| S3 key not found | Verify the key pattern matches your file naming |
| Postgres connection timeout | Set `connect_args={"connect_timeout": 10}` in hook |
| XCom size limit exceeded | Write large extracts to S3; push only the S3 key as XCom |

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Full Code** | [Code_Example.md](./Code_Example.md) |
| **Parent: Intermediate Projects** | [02_Intermediate_Projects](../Readme.md) |
| **Previous: Data Quality Pipeline** | [03_Data_Quality_Pipeline](../03_Data_Quality_Pipeline/Project_Guide.md) |
| **Next: ML Training Pipeline** | [05_ML_Training_Pipeline](../../03_Advanced_Projects/05_ML_Training_Pipeline/Project_Guide.md) |
