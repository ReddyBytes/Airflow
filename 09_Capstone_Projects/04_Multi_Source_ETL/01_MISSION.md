# Project 04 — Multi-Source ETL Pipeline

> **Difficulty:** 🟠 Minimal Hints &nbsp;&nbsp; **Level:** Intermediate &nbsp;&nbsp; **Est. Time:** 4–5 hours
>
> **Skills you will use:** Dynamic Task Mapping (`expand()`), XCom from mapped tasks, TaskGroup, Pools, concurrency control

---

## The Situation

You work at a SaaS company. Every morning the data warehouse needs a fresh snapshot built from three completely independent sources:

- A **PostgreSQL** operational database holding customer orders
- A **REST API** delivering daily exchange rates
- An **S3 bucket** holding partner product-catalogue CSV files

The old approach was three separate DAGs triggered manually in a fixed order. It worked — until someone forgot to run the second one, or the API was slow and the third DAG started reading stale data.

Your job: collapse all three into **one unified pipeline** where extractions run in parallel, the merge waits for all three to finish, and the whole thing runs without anyone touching it.

---

## What You Need to Build

```
SOURCES list (3 configs)
        |
        v
  ┌─────────────────────────────────────┐
  │   extract_source[0]  (HTTP API)     │  ← one task instance per source
  │   extract_source[1]  (S3 CSV)       │    all run in parallel
  │   extract_source[2]  (Postgres)     │
  └──────────────┬──────────────────────┘
                 |
                 v
          merge_sources
          (collects all 3 XCom results)
                 |
                 v
         validate_merged
                 |
                 v
        load_to_warehouse
        (emits WAREHOUSE_ASSET)
```

---

## Key Concepts in Play

**Dynamic Task Mapping** is the engine of this pipeline. Instead of writing three separate extract tasks, you write one `extract_source` function and tell Airflow to run it once per element in `SOURCES`. Each run is a separate task instance, and they all execute in parallel.

The pattern looks like this:

```python
extracted = extract_source.expand(source_config=SOURCES)
# Creates: extract_source[0], extract_source[1], extract_source[2]
# All run in parallel; results collected as a list by the next task
```

When `merge_sources` receives `extracted_results`, it gets back a Python list — one entry per mapped task instance, in index order.

**Pools** protect downstream systems. If all three extractors hammer your Postgres primary at the same time, you have a problem. A pool with a slot limit caps that:

```bash
airflow pools set db_extract_pool 2 "Limits concurrent DB extract tasks"
```

**Assets (Airflow 3)** — the load task declares an outlet so downstream pipelines can trigger automatically when fresh data lands.

---

## Acceptance Criteria

By the end of this project your DAG must:

1. Define a `SOURCES` list with at least three source configs (http, s3, postgres)
2. Use `expand(source_config=SOURCES)` to fan out extractions
3. Each extract function routes on `source_type` and returns a JSON string
4. `merge_sources` receives the list and concatenates all rows into one DataFrame
5. `validate_merged` raises `ValueError` if zero rows or `source_id` column is missing
6. `load_to_warehouse` does a DELETE + INSERT for idempotency and emits an Asset outlet
7. The DAG runs on `@daily`, no `catchup`

---

## Extension Challenges

1. Add a 4th source — just add a dict to `SOURCES`; the DAG auto-adapts with no code change
2. Add a Pool to the expand task so no more than 2 DB extracts run at the same time
3. Replace the daily `schedule` with an Asset-based schedule that triggers when the S3 file lands
4. Add retries and `retry_delay` to the extract task to handle API rate limits

---

⬅️ **Prev:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
