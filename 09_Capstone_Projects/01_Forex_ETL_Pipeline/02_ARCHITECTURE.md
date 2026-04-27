# 02 — Architecture: Forex ETL Pipeline

---

## DAG Task Graph

Think of this as an assembly line. The two sensors run first to confirm all raw materials
(a live API and a config file) are present. Only then does the factory start producing.

```
check_api_availability ──┐
                          ├──► fetch_forex_rates ──► save_rates_to_csv
check_config_file ────────┘          │                      │
                                     │                      ▼
                                     │             create_forex_table
                                     │                      │
                                     │                      ▼
                                     │             load_rates_to_postgres
                                     │                      │
                                     │                      ▼
                                     │             send_summary_email
                                     │                      │
                                     └──────────────────────▼
                                                    cleanup_csv
                                                (trigger_rule=all_done)
```

The `cleanup_csv` task uses `trigger_rule="all_done"` — it runs even if a
task upstream fails, so temp files are never left on disk.

---

## Data Flow

```
exchangerate-api.com                       PostgreSQL
       │                                       │
       │  GET /v6/{key}/latest/USD             │
       │◄──────────────────────────────        │
       │                                       │
       │  {"conversion_rates": {...}}           │
       │──────────────────────────────►        │
       │                                       │
  fetch_forex_rates                            │
  (push to XCom: key="rates")                 │
       │                                       │
       ▼                                       │
  save_rates_to_csv                            │
  (write /tmp/forex/forex_rates_YYYYMMDD.csv)  │
       │                                       │
       ▼                                       │
  create_forex_table                           │
  (CREATE TABLE IF NOT EXISTS forex_rates)     │
       │                                       │
       ▼                                       │
  load_rates_to_postgres  ───────────────────► │
  (INSERT ... ON CONFLICT DO NOTHING)          │
       │                                       │
       ▼                                       │
  send_summary_email                           │
  (pull XCom: rates, row_count)                │
       │                                       │
       ▼                                       │
  cleanup_csv                                  │
  (rm /tmp/forex/forex_rates_YYYYMMDD.csv)     │
```

---

## XCom Map

Tasks pass data to each other via **XCom** (cross-communication), Airflow's
lightweight key-value store for inter-task messaging.

| Producer task | XCom key | Consumer task |
|---|---|---|
| `fetch_forex_rates` | `rates` | `save_rates_to_csv`, `send_summary_email` |
| `fetch_forex_rates` | `base_currency` | `send_summary_email` |
| `save_rates_to_csv` | `csv_path` | `load_rates_to_postgres`, `cleanup_csv` |
| `load_rates_to_postgres` | `rows_inserted` | `send_summary_email` |

---

## Tech Stack

| Component | Role |
|-----------|------|
| Airflow 3 (DAG SDK) | Orchestration |
| `HttpSensor` (providers-http) | Poll API availability |
| `FileSensor` (core) | Wait for config file |
| `HttpHook` | Make authenticated HTTP calls |
| `PostgresOperator` | Run DDL SQL |
| `PostgresHook` | Insert rows with a Python cursor |
| `BashOperator` | Clean up temp files |
| PostgreSQL 15 | Store daily exchange rates |
| exchangerate-api.com | Live forex data source |

---

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS forex_rates (
    id               SERIAL PRIMARY KEY,
    base_currency    VARCHAR(10)    NOT NULL,
    target_currency  VARCHAR(10)    NOT NULL,
    rate             NUMERIC(20, 8) NOT NULL,
    fetched_at       TIMESTAMP      NOT NULL,
    execution_date   DATE           NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forex_rates_date
    ON forex_rates(execution_date);
```

The `UNIQUE` constraint (base, target, execution_date) — combined with
`ON CONFLICT DO NOTHING` — makes every run **idempotent**: re-running the
same day never creates duplicates.

---

## Airflow Connections Required

| Conn ID | Type | Purpose |
|---------|------|---------|
| `forex_api` | HTTP | Base URL for the exchange rate API |
| `forex_postgres` | Postgres | Target database |

---

⬅️ **Prev:** [01 — Mission](./01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [03 — Guide](./03_GUIDE.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
