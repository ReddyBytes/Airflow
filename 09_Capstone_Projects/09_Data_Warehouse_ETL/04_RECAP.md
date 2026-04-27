# Project 09 — Recap

---

## What You Built

A production-pattern daily ETL pipeline that extracts from 3 heterogeneous sources, stages raw data, transforms to a common schema, loads a star schema with SCD Type 1 dimension merges, performs an incremental fact table load, and validates the output.

```
extract.expand(["api","s3","oltp"]) → transform_{api,s3,oltp}
  → dim_loads.[customer,product,date,region] → load_fact_sales → data_quality_check
```

---

## Key Concepts

### Star Schema

The **star schema** is the standard layout for analytical databases (data warehouses). One **fact table** at the center contains the measurements (revenue, quantity, duration). **Dimension tables** around it contain the descriptive attributes (who, what, where, when). Queries become simple: `JOIN` the fact table to whichever dimensions you need, then aggregate.

The shape looks like a star: fact in the middle, dimensions as points. This is by design — analytical queries need wide joins, and a normalized relational schema (many small tables) is slow for that. The star schema trades write efficiency for read efficiency.

### Dynamic Task Mapping

`expand()` is the Airflow 2.3+ way to create N task instances from one task definition. The number of instances can be a static list (as here) or the output of an upstream task. Each instance runs in parallel with its own set of arguments and its own logs. This replaces the old pattern of writing 3 nearly-identical `PythonOperator` definitions.

Key limitation: XCom output from a mapped task is a list of results, one per instance. Downstream tasks receive the whole list. Plan your data handoff accordingly.

### TaskGroups

`TaskGroup` is a visual-only organizational tool — it does not affect execution. All tasks inside a group are displayed collapsed in the Airflow UI. Dependencies defined inside the group still work normally. Use `TaskGroup` when a DAG has more than ~6 tasks; without it, the graph view becomes unreadable.

### SCD Types

| Type | Behavior | Use When |
|---|---|---|
| SCD 0 | Never update | Historical fact data |
| SCD 1 | Overwrite on change | Current state, history irrelevant |
| SCD 2 | Add new row, mark old row inactive | Full history required |
| SCD 3 | Add "previous" column | Only last change matters |

This project uses **SCD Type 1**: when a customer changes their country, we overwrite the old value. No history is kept. This is appropriate when the business question is "what is the customer's current country?" not "what was their country on date X?"

### Incremental Load Pattern

The `DELETE + INSERT` pattern for fact tables is the most portable idempotent load strategy:

1. Delete all rows for `partition_date = today`
2. Insert fresh rows from staging

Re-running the DAG for the same date is safe — it always produces the same result. This is simpler than `INSERT ... ON CONFLICT` for fact tables because fact rows often do not have a single natural unique key.

---

## Extend It

**Add dbt for transforms**
Replace the Python transform tasks with dbt models. Each `stg_*_clean` becomes a dbt staging model, and the star schema tables become dbt models in the `marts/` layer. Use `DbtRunOperator` (from `astronomer-cosmos`) to run dbt from within Airflow. This gives you lineage, documentation, and column-level tests for free.

**Use Snowflake Operator**
Replace `PostgresHook` with `SnowflakeOperator` and `SnowflakeHook`. The `MERGE INTO` statement in Snowflake is more expressive than `INSERT ... ON CONFLICT` and supports SCD Type 2 natively. Snowflake's `COPY INTO` command can load from S3 in seconds.

**Add Great Expectations for data quality**
Replace the custom `data_quality_check` task with a Great Expectations expectation suite. GE integrates with Airflow via `GreatExpectationsOperator`. It produces HTML data docs that show pass/fail status for every assertion, shareable with the business team.

**Add Apache Iceberg for time-travel**
Store the fact table as an Iceberg table (supported by Trino, Spark, Athena). Iceberg's time-travel feature lets you query `SELECT * FROM fact_sales FOR SYSTEM_TIME AS OF '2024-01-15'` — invaluable for debugging why a report looked different last week.

---

## 📂 Navigation

⬅️ **Prev:** [08 — ML Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [10 — Airflow on Kubernetes](../10_Airflow_on_Kubernetes/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
