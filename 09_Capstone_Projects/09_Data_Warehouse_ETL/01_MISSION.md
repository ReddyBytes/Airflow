# Project 09 — Multi-Source Data Warehouse ETL

> Dynamic Task Mapping + TaskGroups + Star Schema | Difficulty: 🟠 Minimal Hints | Time: ~6 hours

---

## The Analogy

Imagine a hotel chain that tracks revenue from three completely different systems: a web booking portal (REST API), nightly exports from their property management system (CSV files on S3), and a legacy Oracle-equivalent database at the corporate office (Postgres OLTP). Every morning, the finance team needs a single consolidated report — but these three systems speak different dialects, use different IDs for the same customer, and arrive at different times.

A **data warehouse** is the single version of truth they need. A **star schema** is the layout that makes it fast to query: one central fact table (transactions, sales, events) surrounded by dimension tables (who, what, where, when). The ETL pipeline is the plumbing that pulls data from the three sources, translates it into the star schema language, and loads it in the right order (dimensions before facts, because the fact table references them).

This project builds that plumbing with the modern Airflow feature set: **dynamic task mapping** to parallelize extracts, **TaskGroups** to keep the DAG visually organized, and an incremental **partitioned fact load** so re-runs don't duplicate data.

---

## Mission

Build an Airflow DAG that:

1. **Extracts** from 3 sources in parallel using `expand()` (dynamic task mapping)
2. **Stages** raw data into Postgres staging tables (`stg_*`)
3. **Transforms** staging data into the star schema shape (per-source logic)
4. **Loads** 4 dimension tables using **SCD Type 1** merge (overwrite on change)
5. **Loads** the fact table incrementally by `partition_date`
6. **Validates** row counts and null checks using a custom assertion task

---

## Skills You Will Practice

| Skill | Where |
|---|---|
| **Dynamic task mapping** | `expand()` — one task definition, N task instances |
| **TaskGroup** | Visual grouping of related tasks in the DAG UI |
| **Airflow connections** | Multiple source connections in one DAG |
| **SCD Type 1** | Dimension table merge: overwrite changed attributes |
| **Incremental load** | Fact table partitioned by `partition_date` |
| **PostgresHook** | Staging and warehouse writes |
| **Data quality assertion** | Row count + null check task |

---

## Prerequisites

Before starting, you should be comfortable with:

- Airflow intermediate: PythonOperator, XCom, connections
- Data modeling: what a star schema is, what dimensions and facts are
- SQL: INSERT, UPDATE, JOIN, MERGE logic (UPSERT patterns)
- Python: `pandas`, `requests`, `boto3` (or `s3fs`)

---

## Acceptance Criteria

You are done when:

- [ ] The DAG renders in the Airflow UI with 3 TaskGroups visible: `extract`, `transform`, `load`
- [ ] `SELECT COUNT(*) FROM stg_api_raw` returns rows after extract runs
- [ ] All 4 dimension tables have rows: `dim_customer`, `dim_product`, `dim_date`, `dim_region`
- [ ] `fact_sales` has rows, and all foreign keys join to dimension tables without NULLs
- [ ] The data quality task passes (green) — no null primary keys, row count above 0
- [ ] Re-running the DAG for the same date does NOT create duplicate fact rows

---

## Difficulty: 🟠 Minimal Hints

Each step gives you one hint — usually the key function or SQL pattern. The rest is yours to design and implement. Consult `src/solution.py` only as a last resort.

---

## Files in This Project

| File | Purpose |
|---|---|
| `01_MISSION.md` | This file |
| `02_ARCHITECTURE.md` | Star schema, ETL flow, TaskGroup diagram |
| `03_GUIDE.md` | 7-step minimal-hint walkthrough |
| `src/starter.py` | TaskGroup scaffold with stubs |
| `src/solution.py` | Complete reference |
| `04_RECAP.md` | Summary, concepts, extensions |

---

## 📂 Navigation

⬅️ **Prev:** [08 — ML Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [10 — Airflow on Kubernetes](../10_Airflow_on_Kubernetes/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
