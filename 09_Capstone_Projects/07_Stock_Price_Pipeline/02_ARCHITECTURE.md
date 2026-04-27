# Project 07 — Architecture

---

## System Overview

The pipeline has two independent processes: a **producer** that runs continuously, and an **Airflow DAG** that runs on a schedule. They are decoupled by Kafka — the producer never waits for Airflow, and Airflow never waits for the producer.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE NETWORK                       │
│                                                                     │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────────┐   │
│  │  producer.py │────▶│  Kafka Broker │────▶│  Airflow DAG     │   │
│  │  (yfinance)  │     │  port 9092    │     │  (consumer)      │   │
│  │              │     │               │     │                  │   │
│  │  every 60s:  │     │  topic:       │     │  every 2 min:    │   │
│  │  AAPL, MSFT  │     │  stock_prices │     │  sensor → proc   │   │
│  │  GOOGL, TSLA │     │               │     │  → MA → upsert   │   │
│  └──────────────┘     │  Zookeeper    │     └────────┬─────────┘   │
│                       │  port 2181    │              │             │
│                       └───────────────┘              ▼             │
│                                               ┌──────────────┐     │
│                                               │  Postgres    │     │
│                                               │  port 5432   │     │
│                                               │  stock_prices│     │
│                                               │  table       │     │
│                                               └──────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## DAG Task Dependency Graph

```
DAG: stock_price_pipeline
Schedule: */2 * * * *  (every 2 minutes)

  ┌─────────────────────────┐
  │   kafka_price_sensor    │  KafkaSensor — waits for ≥1 message
  │   (SensorOperator)      │  in topic "stock_prices"
  └────────────┬────────────┘
               │
               ▼
  ┌─────────────────────────┐
  │   consume_price_batch   │  PythonOperator — reads up to 50 msgs
  │   (PythonOperator)      │  from Kafka, pushes list via XCom
  └────────────┬────────────┘
               │  XCom: List[dict] of ticks
               ▼
  ┌─────────────────────────┐
  │  calculate_moving_avgs  │  PythonOperator — pandas rolling()
  │  (PythonOperator)       │  computes SMA-20 and EMA-12
  └────────────┬────────────┘
               │  XCom: List[dict] with ma_sma20, ma_ema12 added
               ▼
  ┌─────────────────────────┐
  │   upsert_to_postgres    │  PythonOperator — PostgresHook +
  │   (PythonOperator)      │  INSERT ON CONFLICT DO UPDATE
  └─────────────────────────┘
```

---

## Kafka Message Schema

Every message published to the `stock_prices` topic is a JSON object:

```json
{
  "symbol":     "AAPL",
  "price":      189.43,
  "volume":     1204500,
  "timestamp":  "2024-01-15T14:32:00Z",
  "bid":        189.40,
  "ask":        189.46,
  "day_high":   190.12,
  "day_low":    188.55
}
```

**Key:**   `{symbol}_{timestamp}` — ensures each tick is uniquely keyed

**Partition strategy:**   key-based partitioning by symbol, so all AAPL messages land on the same partition (preserving order per symbol)

---

## Postgres Schema

```sql
CREATE TABLE IF NOT EXISTS stock_prices (
    id             SERIAL PRIMARY KEY,
    symbol         VARCHAR(10)    NOT NULL,
    price          NUMERIC(12, 4) NOT NULL,
    volume         BIGINT,
    bid            NUMERIC(12, 4),
    ask            NUMERIC(12, 4),
    day_high       NUMERIC(12, 4),
    day_low        NUMERIC(12, 4),
    ma_sma20       NUMERIC(12, 4),   -- Simple Moving Average, 20-period
    ma_ema12       NUMERIC(12, 4),   -- Exponential Moving Average, 12-period
    recorded_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    inserted_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (symbol, recorded_at)     -- prevents duplicate ticks
);

CREATE INDEX idx_stock_symbol_time ON stock_prices (symbol, recorded_at DESC);
```

The `UNIQUE (symbol, recorded_at)` constraint is what makes the upsert idempotent. If Airflow re-runs a failed task, it will not create duplicate rows — it will update them.

---

## Docker Compose Service Topology

```
docker-compose.yml
│
├── zookeeper          image: confluentinc/cp-zookeeper:7.5.0
│   └── port 2181      Kafka's coordination layer
│
├── kafka              image: confluentinc/cp-kafka:7.5.0
│   ├── port 9092      Broker listener (internal)
│   ├── port 29092     Broker listener (external / host)
│   └── depends_on: zookeeper
│
├── airflow-webserver  image: apache/airflow:2.8.0
│   ├── port 8080      Web UI
│   └── depends_on: airflow-postgres, kafka
│
├── airflow-scheduler  image: apache/airflow:2.8.0
│   └── depends_on: airflow-webserver
│
├── airflow-postgres   image: postgres:15   (Airflow metadata DB)
│   └── port 5433      Exposed on non-default to avoid conflict
│
└── data-postgres      image: postgres:15   (Our stock_prices DB)
    └── port 5432      Standard Postgres port
```

Note: Two separate Postgres instances. `airflow-postgres` stores Airflow's own metadata (DAG runs, task instances, XComs). `data-postgres` stores our pipeline's output.

---

## Data Flow: Tick to Row

```
yfinance.download("AAPL", period="1d", interval="1m")
         │
         │  returns DataFrame with OHLCV columns
         ▼
Extract last row → dict → json.dumps()
         │
         │  message bytes
         ▼
KafkaProducer.send("stock_prices", key=b"AAPL_ts", value=message)
         │
         │  persisted to Kafka log (replicated factor=1 in local dev)
         ▼
Airflow KafkaSensor polls → poke() returns True
         │
         │  sensor completes, downstream tasks unlock
         ▼
KafkaConsumer(topic="stock_prices", max_poll_records=50)
         │
         │  List[ConsumerRecord] → List[dict]
         ▼
XCom.push("ticks", ticks_list)
         │
         ▼
pandas.DataFrame(ticks).groupby("symbol")
    .apply(lambda g: g.assign(
        ma_sma20 = g["price"].rolling(20).mean(),
        ma_ema12 = g["price"].ewm(span=12).mean()
    ))
         │
         │  XCom.push("enriched_ticks", enriched_list)
         ▼
PostgresHook.run(INSERT ... ON CONFLICT (symbol, recorded_at) DO UPDATE ...)
         │
         ▼
Postgres table: stock_prices  ✅
```

---

## 📂 Navigation

⬅️ **Prev:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [08 — ML Model Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
