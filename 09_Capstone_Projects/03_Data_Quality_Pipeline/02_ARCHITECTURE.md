# 02 — Architecture: Data Quality Gate Pipeline

---

## DAG Task Graph

This pipeline acts as a quality gate. Data sits in staging. Nothing moves to
the warehouse until it passes all checks. If it fails, the team is alerted
before anyone queries bad data.

```
check_staging
      │
      ▼
validate_data  (GreatExpectationsOperator)
      │
      │  pushes result dict to XCom (return_json_dict=True)
      ▼
branch_on_quality
      │
      ├── result["success"] == True ────► load_to_warehouse ────────────────────┐
      │                                                                           │
      └── result["success"] == False ──► build_failure_report ► send_alert ─────┤
                                                                                  │
                                                                                  ▼
                                                                        pipeline_complete
                                                          (trigger_rule=none_failed_min_one_success)
```

---

## Data Flow

```
PostgreSQL — staging schema                    PostgreSQL — warehouse schema
        │                                                │
        │  SELECT COUNT(*) WHERE order_date = ds         │
        │◄──────────────────────────────────             │
        │                                                │
   check_staging                                         │
        │ (confirm rows exist, fail fast if not)         │
        ▼                                                │
   validate_data (GX checkpoint)                         │
        │                                                │
        │  SELECT * FROM staging.orders WHERE ...        │
        │◄──────────────────────────────────             │
        │                                                │
        │  6 expectations evaluated                      │
        │  result dict → XCom                            │
        ▼                                                │
   branch_on_quality                                     │
        │                                                │
   PASS │                                                │
        ▼                                                │
   load_to_warehouse ────────────────────────────────────►
        │  INSERT INTO warehouse.orders                  │
        │  WHERE customer_id IS NOT NULL                 │
        │    AND amount >= 0.01                          │
        │  ON CONFLICT (order_id) DO UPDATE ...          │
        │                                                │
   FAIL │                                                │
        ▼                                                │
   build_failure_report                                  │
        │  Read XCom, summarise failed expectations      │
        ▼                                                │
   send_failure_alert (EmailOperator)                    │
        │  HTML email to data-team@company.com           │
        │                                                │
        └──────────────────────────────────► pipeline_complete
```

---

## XCom Map

| Producer task | XCom key | Consumer task |
|---|---|---|
| `check_staging` | `staging_row_count` | (informational, not used downstream) |
| `validate_data` | return value (auto) | `branch_on_quality`, `build_failure_report`, `send_failure_alert` |
| `build_failure_report` | `failure_report` | `send_failure_alert` (via Jinja template) |
| `load_to_warehouse` | `warehouse_row_count` | (informational) |

The `GreatExpectationsOperator` with `return_json_dict=True` and
`fail_task_on_validation_failure=False` pushes the full GX result dict as the
task's return value (which Airflow stores as `return_value` in XCom). The branch
callable pulls it with `ti.xcom_pull(task_ids="validate_data")`.

---

## GX Checkpoint → Airflow Integration

```
GX Expectation Suite (orders_quality_suite)
      │
      │  defines 6 expectations
      ▼
GX Checkpoint (orders_checkpoint)
      │
      │  references suite + datasource
      ▼
GreatExpectationsOperator (Airflow task)
      │
      ├── fail_task_on_validation_failure=False  ← task succeeds regardless
      ├── return_json_dict=True                  ← pushes result to XCom
      └── data_context_root_dir=GX_ROOT
```

Setting `fail_task_on_validation_failure=False` is the critical decision here.
If we let GX fail the task, Airflow would mark the DAG as failed and skip
all downstream tasks — including the alert. By returning the result and routing
manually, we ensure the alert always fires.

---

## Database Schema

```sql
-- Staging (raw ingest — may have quality issues)
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id    TEXT PRIMARY KEY,
    customer_id TEXT,
    amount      NUMERIC(12, 2),
    currency    VARCHAR(3),
    status      TEXT,
    order_date  DATE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Warehouse (clean, validated)
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE TABLE IF NOT EXISTS warehouse.orders (
    order_id     TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL,
    amount       NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    currency     VARCHAR(3),
    status       TEXT,
    order_date   DATE,
    loaded_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Tech Stack

| Component | Role |
|-----------|------|
| Airflow 3 | Orchestration |
| `GreatExpectationsOperator` | Run GX checkpoint in a task |
| `PostgresHook` | Query staging, insert to warehouse |
| `BranchPythonOperator` | Route on GX result |
| `EmailOperator` | Send HTML alert on failure |
| PostgreSQL (staging + warehouse) | Data storage |
| Great Expectations | Expectation suite + checkpoint |

---

⬅️ **Prev:** [01 — Mission](./01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [03 — Guide](./03_GUIDE.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
