# Project 09 — Architecture

---

## Star Schema

```
                          ┌─────────────────┐
                          │   dim_date      │
                          │─────────────────│
                          │ date_key (PK)   │
                          │ full_date       │
                          │ year, month     │
                          │ quarter, week   │
                          │ is_weekend      │
                          └────────┬────────┘
                                   │ FK
                                   │
  ┌─────────────────┐    ┌─────────┴──────────┐    ┌─────────────────┐
  │  dim_customer   │    │    fact_sales       │    │  dim_product    │
  │─────────────────│    │────────────────────│    │─────────────────│
  │ customer_key(PK)│◀───│ sale_id (PK)       │───▶│ product_key(PK) │
  │ customer_id     │    │ customer_key (FK)  │    │ product_id      │
  │ name            │    │ product_key (FK)   │    │ name            │
  │ email           │    │ region_key (FK)    │    │ category        │
  │ country         │    │ date_key (FK)      │    │ price           │
  │ segment         │    │ quantity           │    │ cost            │
  │ created_at      │    │ revenue            │    │ supplier        │
  └─────────────────┘    │ cost               │    └─────────────────┘
                         │ profit             │
                         │ partition_date     │
                         │ source             │
                         └─────────┬──────────┘
                                   │ FK
                                   │
                          ┌────────┴────────┐
                          │   dim_region    │
                          │─────────────────│
                          │ region_key (PK) │
                          │ region_id       │
                          │ region_name     │
                          │ country         │
                          │ continent       │
                          └─────────────────┘
```

---

## ETL Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           EXTRACT GROUP                                  │
│                                                                          │
│  extract_source.expand(source=["api", "s3", "oltp"])                     │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │ extract_source   │  │ extract_source   │  │ extract_source   │       │
│  │ source="api"     │  │ source="s3"      │  │ source="oltp"    │       │
│  │ REST API call    │  │ S3 CSV download  │  │ Postgres query   │       │
│  │ → stg_api_raw    │  │ → stg_s3_raw     │  │ → stg_oltp_raw   │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
│         ▲                      ▲                      ▲                  │
│         └──────────────────────┴──────────────────────┘                 │
│                         all run in PARALLEL                              │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │ all 3 complete
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         TRANSFORM GROUP                                  │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │ transform_api    │  │ transform_s3     │  │ transform_oltp   │       │
│  │ stg_api_raw      │  │ stg_s3_raw       │  │ stg_oltp_raw     │       │
│  │ → stg_api_clean  │  │ → stg_s3_clean   │  │ → stg_oltp_clean │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           LOAD GROUP                                     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Dimension loads (can run in parallel — no dependencies between)   │  │
│  │                                                                    │  │
│  │  load_dim_customer   load_dim_product   load_dim_date              │  │
│  │  load_dim_region     (all use SCD1 merge)                         │  │
│  └────────────────────────────────────┬───────────────────────────────┘  │
│                                       │ all dims complete                 │
│                                       ▼                                  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  load_fact_sales  (incremental, partitioned by partition_date)     │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  data_quality_check    │
              │  row counts + nulls    │
              └────────────────────────┘
```

---

## Dynamic Task Mapping: How `expand()` Works

Standard Airflow (pre-2.3):
```python
# 3 separate task definitions — repetitive
extract_api  = PythonOperator(task_id="extract_api",  ...)
extract_s3   = PythonOperator(task_id="extract_s3",   ...)
extract_oltp = PythonOperator(task_id="extract_oltp", ...)
```

Dynamic task mapping (Airflow 2.3+):
```python
# One definition, N instances — DRY and scalable
@task
def extract_source(source: str) -> str:
    ...

extracted = extract_source.expand(source=["api", "s3", "oltp"])
# Airflow creates 3 task instances at runtime
# extract_source[0], extract_source[1], extract_source[2]
```

The number of instances can even be determined at runtime by passing another task's output to `expand()`.

---

## TaskGroup Nesting

```
DAG: data_warehouse_etl
│
├── extract  (TaskGroup)
│   ├── extract_source[0]  (api)
│   ├── extract_source[1]  (s3)
│   └── extract_source[2]  (oltp)
│
├── transform  (TaskGroup)
│   ├── transform_api
│   ├── transform_s3
│   └── transform_oltp
│
└── load  (TaskGroup)
    ├── dim_loads  (nested TaskGroup)
    │   ├── load_dim_customer
    │   ├── load_dim_product
    │   ├── load_dim_date
    │   └── load_dim_region
    ├── load_fact_sales
    └── data_quality_check
```

---

## SCD Type 1 Merge Pattern

**Slowly Changing Dimension Type 1**: when an attribute changes (customer moves to a new country), overwrite the old value. No history kept. Fast and simple.

```sql
-- SCD Type 1 in Postgres:
INSERT INTO dim_customer (customer_id, name, email, country, segment)
SELECT customer_id, name, email, country, segment
FROM stg_customers_clean
ON CONFLICT (customer_id)
DO UPDATE SET
    name    = EXCLUDED.name,
    email   = EXCLUDED.email,
    country = EXCLUDED.country,
    segment = EXCLUDED.segment;
-- No updated_at tracking needed for SCD1 — just overwrite
```

---

## Incremental Fact Load Pattern

```sql
-- Delete existing rows for this partition before inserting
-- (avoids duplicates on re-run without needing ON CONFLICT on every column)

DELETE FROM fact_sales
WHERE partition_date = '{{ ds }}';

INSERT INTO fact_sales
    (sale_id, customer_key, product_key, region_key, date_key,
     quantity, revenue, cost, profit, partition_date, source)
SELECT
    s.sale_id,
    dc.customer_key,
    dp.product_key,
    dr.region_key,
    dd.date_key,
    s.quantity,
    s.revenue,
    s.cost,
    s.revenue - s.cost AS profit,
    '{{ ds }}'::date    AS partition_date,
    s.source
FROM stg_all_clean s
JOIN dim_customer dc ON dc.customer_id = s.customer_id
JOIN dim_product  dp ON dp.product_id  = s.product_id
JOIN dim_region   dr ON dr.region_id   = s.region_id
JOIN dim_date     dd ON dd.full_date   = s.sale_date;
```

---

## 📂 Navigation

⬅️ **Prev:** [08 — ML Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [10 — Airflow on Kubernetes](../10_Airflow_on_Kubernetes/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
