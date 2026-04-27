# 01 — Data Quality Gate Pipeline

## 🟡 Partially Guided

> **Difficulty:** Intermediate &nbsp;|&nbsp; **Est. Time:** 3–4 hours &nbsp;|&nbsp; **Airflow version:** 3.x

---

## The Story

You're a senior data engineer. Last month, the analytics team's weekly revenue
report was wrong because a null `customer_id` slipped through your ETL. It took
three days to find the bug. The business lost trust in the numbers.

Your manager says: "We need automated data quality checks before anything reaches
the warehouse. If data is bad, quarantine it and alert us immediately."

You build a pipeline with five automated quality checks. If all five pass, the
data flows to the warehouse. If any fail, the bad data goes to a quarantine bucket
and the team gets an email within minutes — before anyone runs a bad report.

---

## What You'll Build

A daily pipeline that sits between your staging database and your warehouse:

| # | Task | Operator | Description |
|---|------|----------|-------------|
| 1 | `check_staging` | PythonOperator | Verify staging rows exist for today |
| 2 | `validate_data` | GreatExpectationsOperator | Run a GX checkpoint with 6 expectations |
| 3 | `branch_on_quality` | BranchPythonOperator | Route on pass/fail |
| 4a | `load_to_warehouse` | PythonOperator | Insert validated rows (idempotent) |
| 4b | `build_failure_report` | PythonOperator | Summarise which expectations failed |
| 4c | `send_failure_alert` | EmailOperator | Email the data team |
| 5 | `pipeline_complete` | EmptyOperator | Convergence point |

---

## Skills You'll Practice

- **GreatExpectationsOperator** — integrating a GX checkpoint into an Airflow task
- **PostgresHook** — querying and inserting with parameterised SQL
- **BranchPythonOperator** — routing on the GX result dict from XCom
- **EmailOperator** — sending HTML failure alerts
- **`trigger_rule="none_failed_min_one_success"`** — converging after a branch
- **Idempotent inserts** — `INSERT ... ON CONFLICT (order_id) DO UPDATE`
- **`fail_task_on_validation_failure=False`** — letting GX return results without
  failing the task, so the branch task can decide what to do

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Airflow 3 running locally | Runtime |
| PostgreSQL accessible | Staging + warehouse databases |
| `apache-airflow-providers-postgres` | PostgresHook |
| `great-expectations` | Validation framework |
| `apache-airflow-providers-great-expectations` | GreatExpectationsOperator |
| Email (SMTP) configured in Airflow | AlertOperator |

```bash
pip install apache-airflow-providers-postgres \
            great-expectations \
            apache-airflow-providers-great-expectations
```

**Airflow connections needed:**
```bash
airflow connections add 'postgres_staging' \
  --conn-type 'postgres' \
  --conn-host 'localhost' \
  --conn-login 'airflow' \
  --conn-password 'airflow' \
  --conn-schema 'airflow' \
  --conn-port 5432

airflow connections add 'postgres_warehouse' \
  --conn-type 'postgres' \
  --conn-host 'localhost' \
  --conn-login 'airflow' \
  --conn-password 'airflow' \
  --conn-schema 'warehouse' \
  --conn-port 5432
```

---

## The 6 Quality Expectations

Your Great Expectations suite checks these rules against `staging.orders`:

| Expectation | Logic | On Failure |
|-------------|-------|-----------|
| Row count ≥ 1 | `expect_table_row_count_to_be_between` | Quarantine |
| `order_id` not null | `expect_column_values_to_not_be_null` | Quarantine |
| `customer_id` not null | `expect_column_values_to_not_be_null` | Quarantine |
| `order_id` unique | `expect_column_values_to_be_unique` | Quarantine |
| `amount` ≥ 0.01 | `expect_column_values_to_be_between` | Quarantine |
| `status` in allowed set | `expect_column_values_to_be_in_set` | Quarantine |

---

## Expected Output

**When all checks pass:**
```
check_staging       → SUCCESS (4 rows for 2024-01-15)
validate_data       → SUCCESS (6/6 expectations met)
branch_on_quality   → routes to load_to_warehouse
load_to_warehouse   → SUCCESS (4 rows loaded)
pipeline_complete   → SUCCESS
```

**When a check fails:**
```
validate_data       → returns result with success=False
branch_on_quality   → routes to build_failure_report
build_failure_report → SUCCESS (report built)
send_failure_alert  → SUCCESS (email sent)
pipeline_complete   → SUCCESS
```

---

## Difficulty Badge

**🟡 Partially Guided** — you need to configure the GX suite and checkpoint
yourself (the guide shows the exact code), but the branching logic and XCom
patterns are left for you to work out with hints.

---

⬅️ **Prev:** [02 — Simple File Processing](../02_Simple_File_Processing/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
