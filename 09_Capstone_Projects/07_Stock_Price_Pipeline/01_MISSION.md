# Project 07 — Real-Time Stock Price Pipeline

> Kafka + Airflow + Postgres | Difficulty: 🟢 Fully Guided | Time: ~4 hours

---

## The Analogy

Think of a stock exchange floor in the 1970s. Runners constantly sprint between trading posts and the ticker tape machine, shouting prices. The ticker tape records everything in sequence — no price is ever lost, they just queue up. A separate analyst sits at a desk, periodically pulling tape off the machine, calculating averages, and writing summaries in a ledger.

That is exactly this pipeline. **yfinance** is the trading floor (prices happen every minute). **Kafka** is the ticker tape (a durable, ordered log). **Airflow** is the analyst (polls on a schedule, processes batches, writes to the ledger). **Postgres** is the ledger — structured, queryable, permanent.

---

## Mission

Build an end-to-end pipeline that:

1. Polls real-time-ish stock prices using **yfinance** every 60 seconds
2. Publishes each tick to a **Kafka topic** (`stock_prices`)
3. Uses Airflow's **KafkaSensor** to detect when new messages are available
4. Consumes the batch with a **PythonOperator**, passing tick data via **XCom**
5. Calculates **Simple Moving Average (SMA-20)** and **Exponential Moving Average (EMA-12)** in Python
6. **Upserts** results into a Postgres `stock_prices` table using **PostgresHook**

By the end you will have a mini trading data platform — the same logical architecture used by Bloomberg terminals, just at a slightly smaller scale.

---

## What You Will Build

```
Producer Script (runs continuously)
    yfinance.download("AAPL", ...) → Kafka Producer → topic: stock_prices

Airflow DAG (runs every 2 minutes)
    KafkaSensor → batch_consumer → calculate_moving_averages → upsert_to_postgres
```

---

## Skills You Will Practice

| Skill | Where |
|---|---|
| **KafkaConsumeSensor** | Waiting for messages before processing |
| **XCom** | Passing tick data between tasks without a file |
| **PostgresHook** | Writing to Postgres from a PythonOperator |
| **SensorOperator pattern** | Polling vs. triggering |
| **Moving averages** | SMA and EMA in Python (pandas) |
| **Docker Compose** | Multi-container local development |
| **ON CONFLICT upsert** | Idempotent Postgres writes |

---

## Prerequisites

Before starting, you should be comfortable with:

- Airflow basics (DAGs, operators, scheduling) — Section 01-03
- What Kafka is conceptually (topic, producer, consumer, offset)
- Basic Postgres SQL (SELECT, INSERT, CREATE TABLE)
- Python: `pandas`, `json`, `datetime`

---

## Acceptance Criteria

You are done when:

- [ ] Running `docker compose up` starts Zookeeper, Kafka, Airflow, and Postgres with no errors
- [ ] The producer script runs and messages appear in `kafka-topics --describe`
- [ ] The Airflow DAG runs end-to-end without red tasks
- [ ] `SELECT * FROM stock_prices ORDER BY recorded_at DESC LIMIT 10;` returns rows
- [ ] SMA_20 and EMA_12 columns are populated (not NULL) after 20+ ticks

---

## Difficulty: 🟢 Fully Guided

Every step has complete code. Your job is to read it, type it (don't copy-paste blindly), understand the `# ← explanation` comments, and answer the reflection questions at the end of each step in `03_GUIDE.md`.

---

## Files in This Project

| File | Purpose |
|---|---|
| `01_MISSION.md` | This file — context and goals |
| `02_ARCHITECTURE.md` | System diagrams and schemas |
| `03_GUIDE.md` | 8-step walkthrough |
| `src/starter.py` | DAG scaffold — fill in the TODOs |
| `src/solution.py` | Complete reference implementation |
| `04_RECAP.md` | Summary, key concepts, extensions |

---

## 📂 Navigation

⬅️ **Prev:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [08 — ML Model Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
