# Recap — Multi-Source ETL Pipeline

---

## What You Built

A single Airflow DAG that replaced three manually-triggered sequential pipelines. It extracts from a REST API, an S3 bucket, and a Postgres database in parallel using dynamic task mapping, merges the three result sets, validates the combined data, and loads it to the warehouse — emitting an Asset on success so downstream pipelines trigger automatically.

---

## Skills Demonstrated

**Dynamic Task Mapping (`expand()`)**

The `SOURCES` list is the entire configuration surface. You defined one `extract_source` function and Airflow created three parallel task instances — one per source. Adding a fourth source requires no DAG code change.

```
extract_source.expand(source_config=SOURCES)
→ extract_source[0]  extract_source[1]  extract_source[2]  (all run in parallel)
```

**XCom from mapped tasks**

When `expand()` creates N task instances, each instance pushes its return value to XCom. The downstream task receives them as a Python list, in index order. The list is passed automatically — no manual `xcom_pull` needed when using the TaskFlow API.

**Idempotent load**

The DELETE + INSERT pattern ensures reruns for the same execution date do not accumulate duplicate rows. This is the baseline for any daily batch pipeline.

**Asset outlet**

`load_to_warehouse` declares `outlets=[WAREHOUSE_ASSET]`. When it succeeds, Airflow marks the asset updated and any DAG scheduled on that asset fires automatically. The ML feature pipeline and the reporting pipeline no longer need a cron schedule or a sensor.

---

## Common Mistakes Made Here

**Mistake: each branch returns a DataFrame, not a JSON string**

DataFrames are not serializable by Airflow's XCom backend. The return value must be a JSON string. Write `df.to_json(orient="records")` at the end of every extractor.

**Mistake: forgetting `source_id` and `source_date` in the extractor**

If these columns are missing, `validate_merged` raises immediately. Add them with `df.insert(0, "source_id", source_id)` before returning.

**Mistake: calling `extract_source()` three times instead of using `expand()`**

Three hard-coded calls defeat the purpose of dynamic task mapping. The graph looks the same in the UI but adding a fourth source now requires a code change.

---

## How This Connects to Real Work

Dynamic task mapping is the Airflow 3 answer to the fan-out pattern. You will see it in:

- Multi-region deployments (one task per region from a list)
- Multi-tenant pipelines (one task per customer)
- File processing (one task per file discovered at runtime)

The SOURCES list pattern extends naturally to any of these.

---

## What to Try Next

The current pipeline is triggered by a daily cron. Try replacing `schedule="@daily"` with `schedule=[s3_file_landed_asset]` where `s3_file_landed_asset` is emitted by a DAG that watches the S3 bucket. The ETL then runs exactly when new partner files arrive — no cron assumptions, no polling.

---

✅ **Completed:** Dynamic Task Mapping, XCom from mapped tasks, Asset outlets, idempotent loads

🔨 **Practice:** Add a 4th source (a Kafka consumer or a SFTP file); observe zero DAG code changes

➡️ **Next project:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md) — KubernetesPodOperator and deferrable operators

---

⬅️ **Prev:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
