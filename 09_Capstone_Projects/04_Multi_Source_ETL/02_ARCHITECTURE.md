# Architecture — Multi-Source ETL Pipeline

---

## The Problem This Solves

Before this pipeline existed, three separate DAGs ran in sequence. An on-call engineer triggered DAG 1, waited, triggered DAG 2, waited, triggered DAG 3. If DAG 1 was slow — say the API was rate-limiting — DAG 2 started reading yesterday's data without anyone knowing.

The fix is parallelism plus a hard dependency: all extractions run at the same time, and the merge step cannot start until every single one succeeds.

---

## Task Dependency Graph

```
SOURCES list
[http_config, s3_config, postgres_config]
         |
         | expand(source_config=SOURCES)
         |
  +------+------+------+
  |             |      |
  v             v      v
extract[0]  extract[1]  extract[2]
(HTTP API)   (S3 CSV)  (Postgres)
  |             |      |
  +------+------+------+
         |
         v (all must succeed — trigger_rule: all_success)
   merge_sources
   (list[str] from XCom)
         |
         v
  validate_merged
  (raise ValueError on empty or missing source_id)
         |
         v
  load_to_warehouse
  (outlets=[WAREHOUSE_ASSET])
```

---

## Data Flow

Each `extract_source` task instance receives one dict from `SOURCES` and returns a JSON string. That string is a list of records — rows from the API, rows from S3, rows from Postgres.

Airflow's dynamic task mapping collects all three return values into a Python list and passes it to `merge_sources` as `extracted_results`. The merge task iterates the list, parses each JSON string into a DataFrame, and concatenates them.

```
extract[0] -> JSON string -> [{"source_id": "exchange_rates", "currency": "EUR", ...}, ...]
extract[1] -> JSON string -> [{"source_id": "product_catalogue", "sku": "...", ...}, ...]
extract[2] -> JSON string -> [{"source_id": "customer_orders", "order_id": "...", ...}, ...]

merge_sources receives: [json_0, json_1, json_2]
                                |
                       pd.concat([df0, df1, df2])
```

Because the three source schemas differ, the merged DataFrame will have many columns and many NaN values in columns that do not apply to a given source. That is intentional — each row carries a `source_id` and `source_date` so downstream consumers can filter by source.

---

## Key Design Choices

**Why `expand()` instead of three hard-coded tasks?**

If you hard-code three tasks, adding a fourth source means editing the DAG code. With `expand()`, you add one dict to `SOURCES`. The DAG automatically creates a fourth task instance next time it parses.

**Why JSON strings over DataFrames in XCom?**

Airflow stores XCom in its metadata database. Pandas DataFrames are not serializable by default and can be large. JSON strings are serializable and keep XCom payloads small. For very large datasets the pattern changes: write to S3, push the S3 key as XCom.

**Why DELETE + INSERT in the load task?**

Idempotency. If the DAG reruns for the same `ds`, you do not accumulate duplicate rows. The DELETE removes the existing partition; the INSERT writes fresh data.

**Why an Asset outlet on `load_to_warehouse`?**

Downstream pipelines (reporting, ML feature extraction) should not poll on a cron schedule hoping the warehouse is ready. They should fire exactly when fresh data lands. The Asset outlet provides that signal.

---

## Concurrency Controls

Without limits, `expand()` will submit all three extract tasks simultaneously. For most sources that is fine. For Postgres, three simultaneous connections to the primary can cause lock contention. Use a Pool:

```
airflow pools set db_extract_pool 2 "Max 2 concurrent DB extract tasks"
```

Assign the pool to the task:
```python
@task(pool="db_extract_pool")
def extract_source(source_config: dict, ds: str = None) -> str:
    ...
```

---

## Airflow Connections Required

| Connection ID      | Type       | Purpose                        |
|--------------------|------------|--------------------------------|
| `aws_default`      | Amazon S3  | Read product catalogue CSVs    |
| `postgres_source`  | Postgres   | Read customer orders           |
| `postgres_warehouse` | Postgres | Write merged results           |

The HTTP source uses `requests` directly with a hardcoded URL — no Airflow connection needed for the exchange rate API.

---

⬅️ **Prev:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
