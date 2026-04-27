# Project 07 — Step-by-Step Guide

> Difficulty: 🟢 Fully Guided. Read the code, understand the comments, type it yourself.
> After each step, answer the reflection question before moving on.

---

## Step 1 — Set Up Kafka with Docker Compose

Create `docker-compose.yml` in the project root:

```yaml
version: "3.8"

services:

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181     # ← Kafka uses this to discover brokers
      ZOOKEEPER_TICK_TIME: 2000
    ports:
      - "2181:2181"

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "29092:29092"                 # ← external port for host-machine access
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1   # ← single broker, so replication=1

  data-postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: stocks
      POSTGRES_PASSWORD: stocks
      POSTGRES_DB: stockdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  airflow-postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    ports:
      - "5433:5432"                   # ← different host port to avoid conflict

  airflow-webserver:
    image: apache/airflow:2.8.0
    depends_on:
      - airflow-postgres
      - kafka
    environment:
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__CORE__FERNET_KEY: ""
      AIRFLOW__WEBSERVER__SECRET_KEY: "stock-pipeline-secret"
    volumes:
      - ./src:/opt/airflow/dags       # ← mounts our DAG files
    ports:
      - "8080:8080"
    command: webserver

  airflow-scheduler:
    image: apache/airflow:2.8.0
    depends_on:
      - airflow-webserver
    environment:
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
    volumes:
      - ./src:/opt/airflow/dags
    command: scheduler

volumes:
  pgdata:
```

Start the stack:

```bash
docker compose up -d
docker compose logs kafka | grep "started"   # ← wait until broker is ready
```

Create the topic manually (Airflow's KafkaSensor won't auto-create it):

```bash
docker exec -it <kafka_container_id> \
  kafka-topics --create \
    --bootstrap-server localhost:9092 \
    --replication-factor 1 \
    --partitions 4 \              # ← 4 partitions: one per symbol (AAPL/MSFT/GOOGL/TSLA)
    --topic stock_prices
```

**Reflection:** Why do we use 4 partitions instead of 1? What does Kafka guarantee within a single partition that it does NOT guarantee across partitions?

---

## Step 2 — Write the Producer Script

Create `src/producer.py`. This runs outside Airflow — it is a standalone Python script you start in a separate terminal:

```python
import json
import time
import yfinance as yf
from datetime import datetime, timezone
from kafka import KafkaProducer

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA"]
KAFKA_BOOTSTRAP = "localhost:29092"   # ← external port from docker-compose

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),   # ← dict → JSON bytes
    key_serializer=lambda k: k.encode("utf-8"),                 # ← string → bytes
)

def fetch_and_publish(symbol: str) -> None:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="1m")           # ← last day, 1-min bars

    if hist.empty:
        print(f"[WARN] No data for {symbol}")
        return

    latest = hist.iloc[-1]                                      # ← most recent bar
    ts = datetime.now(timezone.utc).isoformat()

    message = {
        "symbol":    symbol,
        "price":     round(float(latest["Close"]), 4),
        "volume":    int(latest["Volume"]),
        "day_high":  round(float(latest["High"]), 4),
        "day_low":   round(float(latest["Low"]), 4),
        "timestamp": ts,
    }

    key = f"{symbol}_{ts}"                                      # ← unique key per tick
    producer.send("stock_prices", key=key, value=message)
    producer.flush()                                            # ← block until message is committed
    print(f"[SENT] {symbol} @ {message['price']}")

while True:
    for sym in SYMBOLS:
        fetch_and_publish(sym)
    time.sleep(60)                                              # ← poll every 60 seconds
```

Install dependencies and run:

```bash
pip install yfinance kafka-python
python src/producer.py
```

**Reflection:** Why do we call `producer.flush()` after every send? What happens if we skip it and the script crashes?

---

## Step 3 — Create Airflow Connection for Kafka

In the Airflow UI (localhost:8080, user: `airflow`, pass: `airflow`):

1. Go to **Admin → Connections → Add a new record**
2. Fill in:
   - **Conn ID:** `kafka_default`
   - **Conn Type:** `Apache Kafka`
   - **Extra (JSON):**
     ```json
     {
       "bootstrap.servers": "kafka:9092",
       "group.id": "airflow-stock-consumer",
       "auto.offset.reset": "earliest",
       "enable.auto.commit": false
     }
     ```
3. Click **Save**

Also create the Postgres connection:
- **Conn ID:** `postgres_stocks`
- **Conn Type:** `Postgres`
- **Host:** `data-postgres`
- **Schema:** `stockdb`
- **Login:** `stocks`
- **Password:** `stocks`
- **Port:** `5432`

**Reflection:** Why do we set `enable.auto.commit: false` in the Kafka consumer config? What could go wrong if auto-commit is enabled in an Airflow task?

---

## Step 4 — Write the DAG Structure

Open `src/starter.py` and work through the TODOs. The full task chain looks like this:

```python
from airflow import DAG
from airflow.providers.apache.kafka.sensors.kafka import KafkaSensor
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}

with DAG(
    dag_id="stock_price_pipeline",
    default_args=default_args,
    schedule_interval="*/2 * * * *",    # ← every 2 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kafka", "stocks", "postgres"],
) as dag:

    wait_for_prices = KafkaSensor(...)  # ← Step 5 below
    consume_batch   = PythonOperator(...)
    calculate_mas   = PythonOperator(...)
    upsert_prices   = PythonOperator(...)

    wait_for_prices >> consume_batch >> calculate_mas >> upsert_prices
```

---

## Step 5 — Configure KafkaSensor

The `KafkaSensor` (from `airflow-providers-apache-kafka`) pokes the topic on each `poke_interval`. It returns `True` when its `apply_function` returns a truthy value:

```python
from airflow.providers.apache.kafka.sensors.kafka import KafkaSensor

def check_for_messages(message) -> bool:
    """Called for each message polled during sensor poke."""
    return message is not None              # ← any message means data is ready

wait_for_prices = KafkaSensor(
    task_id="kafka_price_sensor",
    topics=["stock_prices"],                # ← list of topics to watch
    kafka_config_id="kafka_default",        # ← Conn ID from Step 3
    apply_function=check_for_messages,      # ← called per message
    max_messages=1,                         # ← stop after finding 1 message
    poke_interval=15,                       # ← check every 15 seconds
    timeout=120,                            # ← fail after 2 minutes of no data
    mode="poke",                            # ← synchronous poke (simpler)
)
```

**Important:** The KafkaSensor does NOT commit offsets. It just checks if data exists. The actual consumption (with offset commit) happens in the next task.

---

## Step 6 — Write the Batch Consumer and Moving Average Tasks

```python
from kafka import KafkaConsumer
import json

def consume_price_batch(**context) -> None:
    """Reads up to 50 messages from Kafka and pushes to XCom."""
    consumer = KafkaConsumer(
        "stock_prices",
        bootstrap_servers="kafka:9092",
        group_id="airflow-stock-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=False,           # ← we commit manually after processing
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        consumer_timeout_ms=5000,           # ← stop polling after 5s of no messages
    )

    ticks = []
    for msg in consumer:
        ticks.append(msg.value)
        if len(ticks) >= 50:               # ← cap batch size to avoid XCom bloat
            break

    consumer.commit()                       # ← only commit after we've collected the batch
    consumer.close()

    if not ticks:
        raise ValueError("Sensor triggered but no messages found — upstream issue")

    context["ti"].xcom_push(key="ticks", value=ticks)   # ← push to XCom
    print(f"[INFO] Consumed {len(ticks)} ticks")


import pandas as pd

def calculate_moving_averages(**context) -> None:
    """Pulls ticks from XCom, calculates SMA-20 and EMA-12 per symbol."""
    ticks = context["ti"].xcom_pull(task_ids="consume_price_batch", key="ticks")

    df = pd.DataFrame(ticks)
    df["recorded_at"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["symbol", "recorded_at"])          # ← must sort for rolling to make sense

    enriched = []
    for symbol, group in df.groupby("symbol"):
        group = group.copy()
        group["ma_sma20"] = group["price"].rolling(window=20, min_periods=1).mean()
        group["ma_ema12"] = group["price"].ewm(span=12, adjust=False).mean()
        enriched.append(group)

    result = pd.concat(enriched).to_dict(orient="records")
    context["ti"].xcom_push(key="enriched_ticks", value=result)
    print(f"[INFO] Calculated MAs for {len(result)} ticks")
```

**Reflection:** Why do we set `min_periods=1` in the rolling() call? What value would SMA-20 have for the first 19 rows without it?

---

## Step 7 — Write the PostgresHook Upsert

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(10)    NOT NULL,
    price       NUMERIC(12,4)  NOT NULL,
    volume      BIGINT,
    day_high    NUMERIC(12,4),
    day_low     NUMERIC(12,4),
    ma_sma20    NUMERIC(12,4),
    ma_ema12    NUMERIC(12,4),
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    inserted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(symbol, recorded_at)
);
"""

UPSERT_SQL = """
INSERT INTO stock_prices
    (symbol, price, volume, day_high, day_low, ma_sma20, ma_ema12, recorded_at)
VALUES
    (%(symbol)s, %(price)s, %(volume)s, %(day_high)s, %(day_low)s,
     %(ma_sma20)s, %(ma_ema12)s, %(recorded_at)s)
ON CONFLICT (symbol, recorded_at)
DO UPDATE SET
    price    = EXCLUDED.price,
    ma_sma20 = EXCLUDED.ma_sma20,
    ma_ema12 = EXCLUDED.ma_ema12;    -- ← idempotent: re-running updates, never duplicates
"""

def upsert_to_postgres(**context) -> None:
    ticks = context["ti"].xcom_pull(task_ids="calculate_moving_averages", key="enriched_ticks")

    hook = PostgresHook(postgres_conn_id="postgres_stocks")

    with hook.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)        # ← idempotent: IF NOT EXISTS
            for tick in ticks:
                tick["recorded_at"] = tick.get("timestamp") or tick.get("recorded_at")
                cur.execute(UPSERT_SQL, tick)
        conn.commit()

    print(f"[INFO] Upserted {len(ticks)} rows into stock_prices")
```

---

## Step 8 — Test End-to-End

```bash
# 1. Confirm producer is publishing
docker exec -it <kafka_id> \
  kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic stock_prices \
    --from-beginning \
    --max-messages 5

# 2. Trigger the DAG manually from UI or CLI
docker exec -it <airflow_scheduler_id> \
  airflow dags trigger stock_price_pipeline

# 3. Check task logs in UI (localhost:8080) — look for [INFO] lines

# 4. Verify data in Postgres
docker exec -it <data_postgres_id> \
  psql -U stocks -d stockdb -c \
  "SELECT symbol, price, ma_sma20, ma_ema12, recorded_at
   FROM stock_prices
   ORDER BY recorded_at DESC
   LIMIT 10;"
```

Expected output: rows with `symbol`, `price`, and MA columns populated (MA columns will be non-NULL after 12+ ticks per symbol).

**Final reflection:** The KafkaSensor does not commit offsets, but `consume_price_batch` does. What happens if `calculate_moving_averages` fails after the consumer commits? Will those messages ever be re-processed? How would you fix this?

---

## 📂 Navigation

⬅️ **Prev:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [08 — ML Model Retraining Pipeline](../08_ML_Retraining_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
