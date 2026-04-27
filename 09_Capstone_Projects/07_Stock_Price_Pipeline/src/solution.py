"""
Project 07 — Real-Time Stock Price Pipeline
Complete Solution DAG + Producer reference (at bottom, commented out)
"""

import json
from datetime import datetime, timedelta

import pandas as pd
from kafka import KafkaConsumer

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.apache.kafka.sensors.kafka import KafkaSensor
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ─── Default args ─────────────────────────────────────────────────────────────

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}

# ─── Sensor function ──────────────────────────────────────────────────────────

def check_for_messages(message) -> bool:
    """
    Called by KafkaSensor for each message polled from the topic.
    Returning True tells the sensor: "yes, data is here, proceed."
    """
    return message is not None


# ─── Task 2: Consume batch ────────────────────────────────────────────────────

def consume_price_batch(**context) -> None:
    """
    Reads up to 50 messages from the stock_prices Kafka topic.
    Commits offsets only after successfully collecting the full batch.
    Pushes the list of tick dicts to XCom.
    """
    consumer = KafkaConsumer(
        "stock_prices",
        bootstrap_servers="kafka:9092",         # ← internal Docker network address
        group_id="airflow-stock-consumer",
        auto_offset_reset="earliest",           # ← start from beginning if no committed offset
        enable_auto_commit=False,               # ← manual commit for exactly-once semantics
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        consumer_timeout_ms=5000,               # ← stop iterating after 5s with no new messages
    )

    ticks = []
    for msg in consumer:
        ticks.append(msg.value)
        if len(ticks) >= 50:                    # ← cap batch to keep XCom payload manageable
            break

    consumer.commit()                           # ← commit offset only after we have the data
    consumer.close()

    if not ticks:
        raise ValueError("KafkaSensor fired but consume found no messages — check producer")

    context["ti"].xcom_push(key="ticks", value=ticks)
    print(f"[INFO] Consumed {len(ticks)} ticks from Kafka")


# ─── Task 3: Moving averages ──────────────────────────────────────────────────

def calculate_moving_averages(**context) -> None:
    """
    Pulls raw ticks from XCom.
    Groups by symbol, then calculates:
      - SMA-20: simple rolling mean over last 20 prices
      - EMA-12: exponential moving average, span=12
    Pushes enriched tick list back to XCom.
    """
    ticks = context["ti"].xcom_pull(task_ids="consume_price_batch", key="ticks")

    df = pd.DataFrame(ticks)
    df["recorded_at"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["symbol", "recorded_at"])      # ← rolling requires sorted time series

    enriched_groups = []
    for symbol, group in df.groupby("symbol"):
        group = group.copy()
        group["ma_sma20"] = (
            group["price"]
            .rolling(window=20, min_periods=1)          # ← min_periods=1: no NaN on early rows
            .mean()
            .round(4)
        )
        group["ma_ema12"] = (
            group["price"]
            .ewm(span=12, adjust=False)                 # ← adjust=False: recursive formula
            .mean()
            .round(4)
        )
        enriched_groups.append(group)

    enriched = pd.concat(enriched_groups).to_dict(orient="records")

    # Convert Timestamp objects to ISO strings for XCom JSON serialization
    for row in enriched:
        if hasattr(row.get("recorded_at"), "isoformat"):
            row["recorded_at"] = row["recorded_at"].isoformat()

    context["ti"].xcom_push(key="enriched_ticks", value=enriched)
    print(f"[INFO] Moving averages calculated for {len(enriched)} ticks")


# ─── Task 4: Upsert to Postgres ──────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(10)               NOT NULL,
    price       NUMERIC(12, 4)            NOT NULL,
    volume      BIGINT,
    day_high    NUMERIC(12, 4),
    day_low     NUMERIC(12, 4),
    ma_sma20    NUMERIC(12, 4),
    ma_ema12    NUMERIC(12, 4),
    recorded_at TIMESTAMP WITH TIME ZONE  NOT NULL,
    inserted_at TIMESTAMP WITH TIME ZONE  DEFAULT NOW(),
    UNIQUE (symbol, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_stock_symbol_time
    ON stock_prices (symbol, recorded_at DESC);
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
    volume   = EXCLUDED.volume,
    ma_sma20 = EXCLUDED.ma_sma20,
    ma_ema12 = EXCLUDED.ma_ema12;
"""


def upsert_to_postgres(**context) -> None:
    """
    Pulls enriched ticks from XCom and upserts each row into stock_prices.
    ON CONFLICT ensures this is idempotent — safe to retry.
    """
    ticks = context["ti"].xcom_pull(
        task_ids="calculate_moving_averages",
        key="enriched_ticks",
    )

    hook = PostgresHook(postgres_conn_id="postgres_stocks")

    with hook.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)           # ← no-op if table already exists

            for tick in ticks:
                # Normalize the timestamp field name
                if "timestamp" in tick and "recorded_at" not in tick:
                    tick["recorded_at"] = tick["timestamp"]

                # Fill missing optional fields with None (NULL in Postgres)
                tick.setdefault("volume",   None)
                tick.setdefault("day_high", None)
                tick.setdefault("day_low",  None)
                tick.setdefault("ma_sma20", None)
                tick.setdefault("ma_ema12", None)

                cur.execute(UPSERT_SQL, tick)

        conn.commit()

    print(f"[INFO] Upserted {len(ticks)} rows into stock_prices")


# ─── DAG definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="stock_price_pipeline",
    default_args=default_args,
    schedule_interval="*/2 * * * *",            # ← every 2 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kafka", "stocks", "postgres"],
    doc_md="""
    ## Stock Price Pipeline
    Consumes real-time stock ticks from Kafka, calculates moving averages,
    and upserts into Postgres. Producer runs separately (see producer.py).
    """,
) as dag:

    wait_for_prices = KafkaSensor(
        task_id="kafka_price_sensor",
        topics=["stock_prices"],
        kafka_config_id="kafka_default",
        apply_function=check_for_messages,
        max_messages=1,                         # ← just need to confirm data exists
        poke_interval=15,
        timeout=120,
        mode="poke",
    )

    consume_batch = PythonOperator(
        task_id="consume_price_batch",
        python_callable=consume_price_batch,
    )

    calculate_mas = PythonOperator(
        task_id="calculate_moving_averages",
        python_callable=calculate_moving_averages,
    )

    upsert_prices = PythonOperator(
        task_id="upsert_to_postgres",
        python_callable=upsert_to_postgres,
    )

    wait_for_prices >> consume_batch >> calculate_mas >> upsert_prices


# ─── PRODUCER REFERENCE (run separately, not part of DAG) ────────────────────
# Uncomment and run as: python solution.py --producer
#
# import time
# import yfinance as yf
# from datetime import timezone
# from kafka import KafkaProducer
#
# def run_producer():
#     SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA"]
#     producer = KafkaProducer(
#         bootstrap_servers="localhost:29092",
#         value_serializer=lambda v: json.dumps(v).encode("utf-8"),
#         key_serializer=lambda k: k.encode("utf-8"),
#     )
#     while True:
#         for symbol in SYMBOLS:
#             try:
#                 ticker = yf.Ticker(symbol)
#                 hist = ticker.history(period="1d", interval="1m")
#                 if hist.empty:
#                     continue
#                 latest = hist.iloc[-1]
#                 ts = datetime.now(timezone.utc).isoformat()
#                 msg = {
#                     "symbol":    symbol,
#                     "price":     round(float(latest["Close"]), 4),
#                     "volume":    int(latest["Volume"]),
#                     "day_high":  round(float(latest["High"]), 4),
#                     "day_low":   round(float(latest["Low"]), 4),
#                     "timestamp": ts,
#                 }
#                 producer.send("stock_prices", key=f"{symbol}_{ts}", value=msg)
#                 producer.flush()
#                 print(f"[SENT] {symbol} @ {msg['price']}")
#             except Exception as e:
#                 print(f"[ERROR] {symbol}: {e}")
#         time.sleep(60)
