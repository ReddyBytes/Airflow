# 01 — Forex ETL Pipeline

## 🟢 Fully Guided

> **Difficulty:** Beginner &nbsp;|&nbsp; **Est. Time:** 2–3 hours &nbsp;|&nbsp; **Airflow version:** 3.x

---

## The Story

You've just joined a fintech startup as their first data engineer. Every morning the risk team opens a spreadsheet, manually looks up exchange rates on a website, and types them in. It takes 30 minutes and they sometimes copy the wrong number.

Your first task: automate it. Build a pipeline that wakes up at 6am, checks the API is alive, fetches live forex rates, saves them to PostgreSQL, and emails the risk team a clean summary before they've had their coffee.

When you're done, their 30-minute ritual becomes zero minutes.

---

## What You'll Build

A daily **ETL pipeline** (Extract → Transform → Load) with 8 tasks:

| # | Task | Operator | Description |
|---|------|----------|-------------|
| 1 | `check_api_availability` | HttpSensor | Poll the forex API until it responds |
| 2 | `check_config_file` | FileSensor | Wait for the currencies config file to exist |
| 3 | `fetch_forex_rates` | PythonOperator | Call the API, push rates to XCom |
| 4 | `save_rates_to_csv` | PythonOperator | Transform rates into a CSV file |
| 5 | `create_forex_table` | PostgresOperator | Create the DB table if it doesn't exist |
| 6 | `load_rates_to_postgres` | PythonOperator | Insert CSV rows into the table |
| 7 | `send_summary_email` | PythonOperator | Compose and log a stakeholder email |
| 8 | `cleanup_csv` | BashOperator | Remove the temp CSV file |

---

## Skills You'll Practice

- **HttpSensor** — polling an external API for availability before proceeding
- **FileSensor** with `mode="reschedule"` — waiting without blocking a worker slot
- **XCom** — passing data (rates dict, file paths) between tasks
- **PostgresHook** — connecting to Postgres and running parameterised SQL
- **PostgresOperator** — running DDL SQL (CREATE TABLE) from a task
- **BashOperator** — file cleanup with `trigger_rule="all_done"`
- **DAG scheduling** — cron expression `0 6 * * *` (6am UTC daily)
- **Idempotent inserts** — `ON CONFLICT DO NOTHING` so re-runs don't duplicate rows

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Airflow 3 running locally | Runtime |
| Docker Desktop | Run PostgreSQL locally |
| `apache-airflow-providers-http` | HttpSensor + HttpHook |
| `apache-airflow-providers-postgres` | PostgresOperator + PostgresHook |
| Free API key from exchangerate-api.com | Get live forex data |

**Install providers:**
```bash
pip install apache-airflow-providers-http apache-airflow-providers-postgres
```

**Start PostgreSQL with Docker:**
```bash
docker run -d \
  --name forex-postgres \
  -e POSTGRES_USER=airflow \
  -e POSTGRES_PASSWORD=airflow \
  -e POSTGRES_DB=forex \
  -p 5432:5432 \
  postgres:15
```

---

## Expected Output

**PostgreSQL table `forex_rates` after a successful run:**
```
 base_currency | target_currency |    rate    |         fetched_at
---------------+-----------------+------------+----------------------------
 USD           | EUR             | 0.92340000 | 2024-01-15 06:01:23.456789
 USD           | GBP             | 0.78910000 | 2024-01-15 06:01:23.456789
 USD           | JPY             | 148.45000  | 2024-01-15 06:01:23.456789
```

**Logged summary:**
```
SUBJECT: Forex Rates Loaded — 2024-01-15

Base currency: USD
Rates loaded: 7
  USD/EUR: 0.9234
  USD/GBP: 0.7891
  USD/JPY: 148.4500
```

---

## Difficulty Badge

**🟢 Fully Guided** — every step is explained. The starter file has TODO comments that guide you to the exact lines to fill in. The solution file shows the complete answer.

---

➡️ **Next:** [02 — Simple File Processing](../02_Simple_File_Processing/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
