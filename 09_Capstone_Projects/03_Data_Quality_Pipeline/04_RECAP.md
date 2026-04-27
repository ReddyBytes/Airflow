# 04 — Recap: Data Quality Gate Pipeline

---

## What You Built

A data quality gate that sits between your staging database and your warehouse:

1. Verifies staging data exists before spending time on validation
2. Runs 6 automated expectations through a Great Expectations checkpoint
3. Routes to either load (all pass) or alert (any fail)
4. Sends a structured HTML failure email that names the exact failing expectations
5. Loads only clean, validated rows — idempotently

---

## Key Concepts Reinforced

**`fail_task_on_validation_failure=False`** — the most important setting in this
project. If GX fails the task, Airflow marks all downstream tasks as "upstream_failed"
and skips them — including your alert task. That defeats the whole purpose. By
keeping the task green and routing manually via `BranchPythonOperator`, the alert
always fires when it should.

**Staging → warehouse pattern** — this is industry standard. Raw data lands in
staging (no constraints), gets validated, and only clean rows move to the warehouse
(strict constraints). The warehouse's `NOT NULL` and `CHECK` constraints are a
last line of defence, not the primary validation layer.

**Idempotent inserts with `ON CONFLICT DO UPDATE`** — the load task can be
re-triggered any number of times without creating duplicates. If the warehouse
already has a row for an `order_id`, the INSERT updates the `amount`, `status`,
and `loaded_at` instead of failing. This means a fix-and-rerun workflow is always safe.

**Great Expectations vs custom checks** — GX gives you a reusable, versioned,
documented expectation suite with an auto-generated Data Docs report. The custom
checks in Project 02 are fine for small pipelines; GX is what you'd use in a
team with many datasets and multiple engineers.

**`EmptyOperator` as a convergence point** — using an `EmptyOperator` (does nothing)
as the final `pipeline_complete` task is a clean pattern for signalling that the
pipeline has finished, regardless of which branch ran. It's also easy to add SLAs
or callbacks to this single terminal task.

---

## Operators Used

| Operator | Module | What it does here |
|----------|--------|--------------------|
| `PythonOperator` | `airflow.operators.python` | Check staging, load warehouse, build report |
| `GreatExpectationsOperator` | `great_expectations_provider.operators` | Run GX checkpoint |
| `BranchPythonOperator` | `airflow.operators.python` | Route on GX result |
| `EmailOperator` | `airflow.operators.email` | Send HTML failure alert |
| `EmptyOperator` | `airflow.operators.empty` | Convergence / terminal marker |

---

## Extend It

1. **Add a data diff check** — compare today's row count to yesterday's
   (`±20%` tolerance). A sudden spike or drop in rows is often a sign of
   upstream pipeline failure.

2. **Generate an HTML quality report** — the GX result dict contains
   `result["results"]` with per-expectation detail. Write this to an HTML
   file, upload to S3, and include the presigned URL in the failure email.

3. **Add a re-run sensor** — after a quarantine, add a `FileSensor` or
   `SqlSensor` that waits for the vendor to re-upload a fixed file, then
   re-trigger the validation automatically.

4. **Replace custom checks with GX entirely** — remove the `check_staging`
   Python task and add a `expect_table_row_count_to_be_between(min_value=1)`
   expectation to the suite instead. One fewer moving part.

5. **Add a TaskGroup for the failure path** — wrap `build_failure_report` and
   `send_failure_alert` in a `TaskGroup("handle_failure")` for cleaner UI grouping.

---

## Files in This Project

```
03_Data_Quality_Pipeline/
├── 01_MISSION.md       ← what/why/prerequisites
├── 02_ARCHITECTURE.md  ← DAG graph, GX integration, data flow
├── 03_GUIDE.md         ← step-by-step guide with hints
├── src/
│   ├── starter.py      ← scaffold with TODO comments
│   └── solution.py     ← complete working DAG
└── 04_RECAP.md         ← you are here
```

---

⬅️ **Prev:** [02 — Simple File Processing](../02_Simple_File_Processing/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
