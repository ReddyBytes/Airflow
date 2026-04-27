# Project 07 — Recap

---

## What You Built

A four-task Airflow DAG that acts as the "analyst" in a real-time trading data system. The producer and the consumer are decoupled by Kafka, which means either side can go down and restart without losing data. The pipeline calculates moving averages in Python using pandas and writes results idempotently to Postgres.

```
KafkaSensor → consume_price_batch → calculate_moving_averages → upsert_to_postgres
```

---

## Key Concepts

### Sensors vs Triggers

A **sensor** is an operator that loops — it pokes a condition on an interval and holds the task slot until the condition is true. Use sensors when you need to wait for an external event (file appears, API returns data, Kafka topic has messages) before downstream work can begin.

The alternative is **event-driven triggering**: an external system calls the Airflow API to trigger a DAG run directly. Sensors are simpler to set up but consume a worker slot while waiting. Use `mode="reschedule"` on long-running sensors to release the slot between pokes.

### KafkaSensor Pattern

The `KafkaSensor` does not process messages — it only confirms they exist. The actual consumption with offset management happens in the next task. This separation is intentional: the sensor is stateless and safe to retry; the consumer does stateful work (commits offsets) and should be idempotent via `ON CONFLICT`.

### Moving Averages: Python vs SQL

| Approach | Pros | Cons |
|---|---|---|
| Python (pandas) | Flexible, easy EMA with `ewm()` | Loads data into memory |
| SQL (`AVG() OVER`) | Stays in database, no data transfer | No EMA natively, complex window frames |
| Hybrid | Calculate in Python, store result | Extra storage column per metric |

This project uses the hybrid approach: calculate in Python, store the result in dedicated MA columns.

### XCom for Tick Data

XCom is Airflow's built-in inter-task communication. It stores values in the metadata database. For small batches (≤50 JSON ticks), this is fine. For larger payloads, use an **XCom backend** (S3 or GCS) or pass a file path instead of the data itself.

### ON CONFLICT Upsert

The `INSERT ... ON CONFLICT ... DO UPDATE` pattern (PostgreSQL) makes the write operation idempotent. If a DAG run fails after writing some rows and retries from the start, the re-inserted rows will simply update in place rather than raising a duplicate key error. This is the correct default for any pipeline that may retry.

---

## Extend It

**Add Redis for a real-time price cache**
After each upsert, write the latest price per symbol to Redis with a 90-second TTL. A separate API can then read Redis for sub-second latency without hitting Postgres on every request.

**Add a Grafana dashboard**
Connect Grafana to `data-postgres` and build a dashboard that plots `price`, `ma_sma20`, and `ma_ema12` as time series per symbol. Add a threshold alert when price crosses below EMA-12 (bearish signal).

**Replace Airflow consumer with Apache Flink**
Airflow operates in 2-minute batches. For sub-second latency, replace the consumer with a Flink job (PyFlink or Java) that reads from Kafka continuously and writes to Postgres using JDBC sink. Keep Airflow for orchestrating the Flink job itself (submit, monitor, restart on failure).

**Add dead-letter queue handling**
Wrap the Kafka consume loop in a try/except. Messages that fail JSON deserialization or schema validation should be published to a `stock_prices_dlq` topic rather than dropped silently. Add a separate Airflow DAG that processes the DLQ daily.

---

## 📂 Navigation

⬅️ **Prev:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [08 — ML Model Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
