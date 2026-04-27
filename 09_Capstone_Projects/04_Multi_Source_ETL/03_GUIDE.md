# Guide — Multi-Source ETL Pipeline

---

## Before You Start

Read `01_MISSION.md` and `02_ARCHITECTURE.md` first. Understand the task graph and data flow before opening an editor.

Set up the required Airflow connections:

```bash
airflow connections add aws_default \
    --conn-type aws \
    --conn-extra '{"region_name": "us-east-1"}'

airflow connections add postgres_source \
    --conn-type postgres \
    --conn-host localhost \
    --conn-login airflow \
    --conn-password airflow \
    --conn-port 5432 \
    --conn-schema orders_db

airflow connections add postgres_warehouse \
    --conn-type postgres \
    --conn-host localhost \
    --conn-login airflow \
    --conn-password airflow \
    --conn-port 5432 \
    --conn-schema warehouse
```

Create the warehouse table before first run:

```sql
CREATE SCHEMA IF NOT EXISTS warehouse;

CREATE TABLE IF NOT EXISTS warehouse.multi_source_daily (
    source_id       TEXT,
    source_date     DATE,
    _extract_index  INTEGER,
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msd_source_date
    ON warehouse.multi_source_daily (source_date);
```

---

## Step 1 — Define Your Sources

Create the `SOURCES` list. Each dict must have a `source_type` key so the extract function can route to the correct extractor. The other keys depend on the type.

Minimal shape:

```python
SOURCES = [
    {"source_type": "http",     "source_id": "exchange_rates",    ...},
    {"source_type": "s3",       "source_id": "product_catalogue", ...},
    {"source_type": "postgres", "source_id": "customer_orders",   ...},
]
```

Hint: the HTTP source should use `requests.get()`. The S3 source needs `S3Hook`. The Postgres source needs `PostgresHook`.

---

## Step 2 — Write the Extract Task

Write a single `extract_source` function decorated with `@task`. It receives one dict from `SOURCES` and a `ds` string (the execution date). It must return a JSON string representing a list of records.

The routing logic:

```python
@task
def extract_source(source_config: dict, ds: str = None) -> str:
    stype = source_config["source_type"]
    if stype == "http":
        # TODO: fetch with requests, flatten response into rows, return json.dumps(rows)
    elif stype == "s3":
        # TODO: read CSV via S3Hook, add source_id and source_date columns, return df.to_json()
    elif stype == "postgres":
        # TODO: query via PostgresHook, add source_id and source_date, return df.to_json()
    else:
        raise ValueError(f"Unknown source_type: {stype!r}")
```

Each branch must insert a `source_id` and `source_date` column so the merge step can track lineage.

---

## Step 3 — Fan Out with `expand()`

In the DAG body, call `expand()` to create one task instance per source config:

```python
extracted = extract_source.expand(source_config=SOURCES)
# extracted is a list of 3 JSON strings at runtime
```

That is the entire dynamic mapping setup. Do not call `extract_source` three times manually.

---

## Step 4 — Write the Merge Task

`merge_sources` receives `extracted_results: list[str]`. Iterate the list, parse each JSON string into a DataFrame, and concatenate:

```python
@task
def merge_sources(extracted_results: list[str]) -> str:
    frames = []
    for idx, payload in enumerate(extracted_results):
        df = pd.DataFrame(json.loads(payload))
        df["_extract_index"] = idx  # ← preserve which task produced this slice
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    print(f"[merge] {len(merged)} total rows from {len(frames)} sources")
    return merged.to_json(orient="records", date_format="iso")
```

---

## Step 5 — Write Validate and Load Tasks

Validation must raise `ValueError` on two conditions:

1. Zero rows after merge
2. `source_id` column missing or containing nulls

Everything else can be a warning (`print`), not a failure.

Load must be idempotent:

```python
# Delete today's partition before inserting
hook.run(
    "DELETE FROM warehouse.multi_source_daily WHERE source_date = %s",
    parameters=[ds],
)
# Then insert fresh rows
```

Attach the Asset outlet to `load_to_warehouse`:

```python
WAREHOUSE_ASSET = Asset("postgres://warehouse/multi_source_daily")

@task(outlets=[WAREHOUSE_ASSET])
def load_to_warehouse(validated_json: str, ds: str = None) -> int:
    ...
```

---

## Step 6 — Assemble the DAG

```python
with DAG(
    dag_id="multi_source_etl",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["capstone", "dynamic-mapping", "etl"],
) as dag:
    extracted = extract_source.expand(source_config=SOURCES)
    merged    = merge_sources(extracted_results=extracted)
    validated = validate_merged(merged_json=merged)
    load_to_warehouse(validated_json=validated)
```

---

## Step 7 — Verify in the UI

Trigger manually:

```bash
airflow dags trigger multi_source_etl --exec-date 2024-01-15
```

In the graph view you should see three instances of `extract_source` — `[0]`, `[1]`, `[2]` — running in parallel, then a single `merge_sources`, `validate_merged`, and `load_to_warehouse`.

Click any `extract_source` instance and open the **Mapped Tasks** tab to see which source config it processed.

---

## Common Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| All three extracts run but merge gets `None` | XCom too large | Write data to S3, push only the S3 key |
| `extract[1]` fails with S3 key not found | Date format mismatch in key template | Check that `ds` is formatted as `YYYY-MM-DD` |
| Postgres connection timeout | Pool too large | Add `connect_args={"connect_timeout": 10}` to hook |
| `merge_sources` gets a list of `None` | Extract function missing `return` | Add `return json.dumps(rows)` to all branches |

---

## Where to Go Next

When the pipeline is green end-to-end, attempt the extension challenges in `01_MISSION.md`. The most instructive one is replacing the daily cron with an Asset-based schedule that fires when the S3 file lands.

Then open `src/solution.py` to compare your implementation.

---

⬅️ **Prev:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
