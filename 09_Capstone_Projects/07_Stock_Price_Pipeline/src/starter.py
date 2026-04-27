"""
Project 07 — Real-Time Stock Price Pipeline
DAG Starter: Fill in all TODO sections before looking at solution.py
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

# TODO: Import KafkaSensor from the apache kafka provider
# Hint: airflow.providers.apache.kafka.sensors.kafka

# TODO: Import PostgresHook from the postgres provider

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}


# ─── Sensor apply function ────────────────────────────────────────────────────

def check_for_messages(message):
    """
    TODO: Return True if message is not None.
    This function is called by KafkaSensor for each polled message.
    Returning True stops the sensor and marks it successful.
    """
    # TODO: implement
    pass


# ─── Task 2: Consume batch from Kafka ────────────────────────────────────────

def consume_price_batch(**context):
    """
    TODO:
    1. Create a KafkaConsumer connected to 'kafka:9092', topic 'stock_prices'
    2. Poll up to 50 messages, deserializing JSON values
    3. Commit offsets manually after collecting the batch
    4. Push the list of tick dicts to XCom with key='ticks'
    5. Raise ValueError if no messages found
    """
    # TODO: implement
    pass


# ─── Task 3: Calculate moving averages ───────────────────────────────────────

def calculate_moving_averages(**context):
    """
    TODO:
    1. Pull 'ticks' from XCom (task_ids='consume_price_batch')
    2. Build a DataFrame, sort by symbol + recorded_at
    3. For each symbol group:
       - SMA-20: rolling(window=20, min_periods=1).mean()
       - EMA-12: ewm(span=12, adjust=False).mean()
    4. Push enriched list to XCom with key='enriched_ticks'
    """
    # TODO: implement
    pass


# ─── Task 4: Upsert to Postgres ──────────────────────────────────────────────

CREATE_TABLE_SQL = """
-- TODO: Write the CREATE TABLE IF NOT EXISTS statement for stock_prices
-- Columns: id (serial pk), symbol, price, volume, day_high, day_low,
--          ma_sma20, ma_ema12, recorded_at, inserted_at
-- Add UNIQUE constraint on (symbol, recorded_at)
"""

UPSERT_SQL = """
-- TODO: Write INSERT ... ON CONFLICT (symbol, recorded_at) DO UPDATE
-- Update: price, ma_sma20, ma_ema12 using EXCLUDED.*
"""

def upsert_to_postgres(**context):
    """
    TODO:
    1. Pull 'enriched_ticks' from XCom (task_ids='calculate_moving_averages')
    2. Use PostgresHook(postgres_conn_id='postgres_stocks')
    3. Execute CREATE_TABLE_SQL first (idempotent)
    4. Loop through ticks, execute UPSERT_SQL for each
    5. Commit the transaction
    """
    # TODO: implement
    pass


# ─── DAG definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="stock_price_pipeline",
    default_args=default_args,
    schedule_interval="*/2 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kafka", "stocks", "postgres"],
) as dag:

    # TODO: Define KafkaSensor task 'kafka_price_sensor'
    # - topics: ["stock_prices"]
    # - kafka_config_id: "kafka_default"
    # - apply_function: check_for_messages
    # - max_messages: 1
    # - poke_interval: 15
    # - timeout: 120
    wait_for_prices = None  # TODO: replace with KafkaSensor(...)

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

    # TODO: Wire up the task dependencies
    # wait_for_prices >> consume_batch >> calculate_mas >> upsert_prices
