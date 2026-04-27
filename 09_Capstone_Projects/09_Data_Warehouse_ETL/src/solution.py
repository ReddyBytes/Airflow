"""
Project 09 — Multi-Source Data Warehouse ETL
Complete Solution DAG
"""

import json
import requests
import pandas as pd
from datetime import datetime, timedelta, date

from airflow.decorators import dag, task
from airflow.utils.task_group import TaskGroup
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

WAREHOUSE_CONN = "postgres_warehouse"


# ─── Schema setup (run once at startup) ──────────────────────────────────────

SCHEMA_SQL = """
-- Staging tables (permissive schema, TEXT columns)
CREATE TABLE IF NOT EXISTS stg_api_raw  (data JSONB, loaded_at TIMESTAMP DEFAULT NOW());
CREATE TABLE IF NOT EXISTS stg_s3_raw   (data JSONB, loaded_at TIMESTAMP DEFAULT NOW());
CREATE TABLE IF NOT EXISTS stg_oltp_raw (data JSONB, loaded_at TIMESTAMP DEFAULT NOW());

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key SERIAL PRIMARY KEY,
    customer_id  TEXT UNIQUE NOT NULL,
    name         TEXT,
    email        TEXT,
    country      TEXT,
    segment      TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key  SERIAL PRIMARY KEY,
    product_id   TEXT UNIQUE NOT NULL,
    name         TEXT,
    category     TEXT,
    price        NUMERIC(12,4),
    cost         NUMERIC(12,4),
    supplier     TEXT
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key  SERIAL PRIMARY KEY,
    full_date DATE UNIQUE NOT NULL,
    year      INT,
    month     INT,
    quarter   INT,
    week      INT,
    is_weekend BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_region (
    region_key   SERIAL PRIMARY KEY,
    region_id    TEXT UNIQUE NOT NULL,
    region_name  TEXT,
    country      TEXT,
    continent    TEXT
);

CREATE TABLE IF NOT EXISTS fact_sales (
    sale_id        TEXT,
    customer_key   INT,
    product_key    INT,
    region_key     INT,
    date_key       INT,
    quantity       INT,
    revenue        NUMERIC(12,4),
    cost           NUMERIC(12,4),
    profit         NUMERIC(12,4),
    partition_date DATE NOT NULL,
    source         TEXT,
    PRIMARY KEY (sale_id, partition_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_partition ON fact_sales (partition_date);
"""


def ensure_schema():
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    hook.run(SCHEMA_SQL)


# ─── Extract ──────────────────────────────────────────────────────────────────

@task
def extract_source(source: str, **context) -> str:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    ensure_schema()

    if source == "api":
        # Public mock API — replace with real endpoint in production
        resp = requests.get("https://fakestoreapi.com/products", timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        hook.run("DELETE FROM stg_api_raw;")   # ← truncate before fresh load
        for row in rows:
            hook.run(
                "INSERT INTO stg_api_raw (data) VALUES (%s)",
                parameters=[json.dumps(row)],
            )
        print(f"[INFO] Extracted {len(rows)} rows from API → stg_api_raw")
        return "stg_api_raw"

    elif source == "s3":
        # Simulated S3 extract using synthetic data (replace with boto3 in production)
        import io
        synthetic_csv = "customer_id,product_id,region_id,sale_date,quantity,revenue\n"
        for i in range(50):
            synthetic_csv += f"CUST-{i % 10:04d},PROD-{i % 5:04d},REG-{i % 3:02d},"
            synthetic_csv += f"{context['ds']},{i % 10 + 1},{(i+1) * 19.99:.2f}\n"

        df = pd.read_csv(io.StringIO(synthetic_csv))
        hook.run("DELETE FROM stg_s3_raw;")
        for _, row in df.iterrows():
            hook.run(
                "INSERT INTO stg_s3_raw (data) VALUES (%s)",
                parameters=[json.dumps(row.to_dict())],
            )
        print(f"[INFO] Extracted {len(df)} rows from S3 → stg_s3_raw")
        return "stg_s3_raw"

    elif source == "oltp":
        # Simulated OLTP source — in production: PostgresHook("postgres_oltp").get_records(...)
        synthetic = []
        for i in range(30):
            synthetic.append({
                "customer_id": f"CUST-{i % 8:04d}",
                "product_id":  f"PROD-{i % 4:04d}",
                "region_id":   f"REG-{i % 2:02d}",
                "sale_date":   context["ds"],
                "quantity":    (i % 5) + 1,
                "revenue":     round((i + 1) * 25.50, 2),
            })
        hook.run("DELETE FROM stg_oltp_raw;")
        for row in synthetic:
            hook.run(
                "INSERT INTO stg_oltp_raw (data) VALUES (%s)",
                parameters=[json.dumps(row)],
            )
        print(f"[INFO] Extracted {len(synthetic)} rows from OLTP → stg_oltp_raw")
        return "stg_oltp_raw"

    raise ValueError(f"Unknown source: {source}")


# ─── Transform ────────────────────────────────────────────────────────────────

def _read_staging_table(hook: PostgresHook, table: str) -> pd.DataFrame:
    rows = hook.get_records(f"SELECT data FROM {table}")
    return pd.DataFrame([r[0] for r in rows])


def _write_clean_table(hook: PostgresHook, df: pd.DataFrame, clean_table: str) -> None:
    hook.run(f"DROP TABLE IF EXISTS {clean_table};")
    cols = ", ".join(f"{c} TEXT" for c in df.columns)
    hook.run(f"CREATE TABLE {clean_table} ({cols});")
    for _, row in df.iterrows():
        placeholders = ", ".join(["%s"] * len(row))
        hook.run(
            f"INSERT INTO {clean_table} VALUES ({placeholders})",
            parameters=list(row.astype(str)),
        )


def transform_api(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    df = _read_staging_table(hook, "stg_api_raw")

    if df.empty:
        raise ValueError("stg_api_raw is empty — extract may have failed")

    # FakeStoreAPI schema normalization
    clean = pd.DataFrame({
        "product_id":  df["id"].astype(str).apply(lambda x: f"API-PROD-{x}"),
        "name":        df.get("title", ""),
        "category":    df.get("category", ""),
        "price":       df.get("price", 0),
        "cost":        (df.get("price", 0).astype(float) * 0.6).round(2),
        "supplier":    "API-Source",
    })
    _write_clean_table(hook, clean, "stg_api_clean")
    print(f"[INFO] Transformed {len(clean)} rows → stg_api_clean")


def transform_s3(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    df = _read_staging_table(hook, "stg_s3_raw")

    if df.empty:
        raise ValueError("stg_s3_raw is empty")

    # Normalize date format, standardize IDs
    df["sale_date"] = pd.to_datetime(df["sale_date"]).dt.strftime("%Y-%m-%d")
    _write_clean_table(hook, df, "stg_s3_clean")
    print(f"[INFO] Transformed {len(df)} rows → stg_s3_clean")


def transform_oltp(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    df = _read_staging_table(hook, "stg_oltp_raw")

    if df.empty:
        raise ValueError("stg_oltp_raw is empty")

    df["sale_date"] = pd.to_datetime(df["sale_date"]).dt.strftime("%Y-%m-%d")
    _write_clean_table(hook, df, "stg_oltp_clean")
    print(f"[INFO] Transformed {len(df)} rows → stg_oltp_clean")


# ─── Dimension loads ──────────────────────────────────────────────────────────

def load_dim_customer(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    # Collect unique customers from all clean staging tables that have customer data
    customers = []
    for table in ("stg_s3_clean", "stg_oltp_clean"):
        try:
            rows = hook.get_records(
                f"SELECT DISTINCT customer_id FROM {table} WHERE customer_id IS NOT NULL"
            )
            for (cid,) in rows:
                customers.append({
                    "customer_id": cid,
                    "name":    f"Customer {cid}",   # real pipeline: join to CRM
                    "email":   f"{cid.lower()}@example.com",
                    "country": "US",
                    "segment": "Standard",
                })
        except Exception as e:
            print(f"[WARN] Could not read {table}: {e}")

    for c in customers:
        hook.run(
            """
            INSERT INTO dim_customer (customer_id, name, email, country, segment)
            VALUES (%(customer_id)s, %(name)s, %(email)s, %(country)s, %(segment)s)
            ON CONFLICT (customer_id) DO UPDATE SET
                name    = EXCLUDED.name,
                email   = EXCLUDED.email,
                country = EXCLUDED.country,
                segment = EXCLUDED.segment;
            """,
            parameters=c,
        )
    print(f"[INFO] Upserted {len(customers)} customers → dim_customer")


def load_dim_product(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)

    # Products from API clean table
    try:
        rows = hook.get_records(
            "SELECT product_id, name, category, price, cost, supplier FROM stg_api_clean"
        )
    except Exception:
        rows = []

    # Synthetic products for S3/OLTP sources
    synthetic = [
        {"product_id": f"PROD-{i:04d}", "name": f"Product {i}", "category": "General",
         "price": round(i * 10.0, 2), "cost": round(i * 6.0, 2), "supplier": "Internal"}
        for i in range(10)
    ]

    for row in rows:
        hook.run(
            """
            INSERT INTO dim_product (product_id, name, category, price, cost, supplier)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id) DO UPDATE SET
                name=EXCLUDED.name, category=EXCLUDED.category,
                price=EXCLUDED.price, cost=EXCLUDED.cost;
            """,
            parameters=list(row),
        )
    for p in synthetic:
        hook.run(
            """
            INSERT INTO dim_product (product_id, name, category, price, cost, supplier)
            VALUES (%(product_id)s, %(name)s, %(category)s, %(price)s, %(cost)s, %(supplier)s)
            ON CONFLICT (product_id) DO UPDATE SET
                name=EXCLUDED.name, category=EXCLUDED.category;
            """,
            parameters=p,
        )
    print(f"[INFO] Loaded products → dim_product")


def load_dim_date(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    # Generate a full year of date rows
    date_range = pd.date_range(start="2023-01-01", end="2025-12-31", freq="D")
    for d in date_range:
        hook.run(
            """
            INSERT INTO dim_date (full_date, year, month, quarter, week, is_weekend)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (full_date) DO NOTHING;
            """,
            parameters=[
                d.date(), d.year, d.month,
                d.quarter, d.isocalendar()[1],
                d.dayofweek >= 5,
            ],
        )
    print(f"[INFO] Loaded {len(date_range)} date rows → dim_date")


def load_dim_region(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    regions = [
        {"region_id": "REG-00", "region_name": "North America", "country": "US",    "continent": "Americas"},
        {"region_id": "REG-01", "region_name": "Europe West",   "country": "DE",    "continent": "Europe"},
        {"region_id": "REG-02", "region_name": "Asia Pacific",  "country": "SG",    "continent": "Asia"},
    ]
    for r in regions:
        hook.run(
            """
            INSERT INTO dim_region (region_id, region_name, country, continent)
            VALUES (%(region_id)s, %(region_name)s, %(country)s, %(continent)s)
            ON CONFLICT (region_id) DO UPDATE SET
                region_name=EXCLUDED.region_name, country=EXCLUDED.country;
            """,
            parameters=r,
        )
    print(f"[INFO] Loaded {len(regions)} regions → dim_region")


# ─── Fact load ────────────────────────────────────────────────────────────────

def load_fact_sales(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    partition_date = context["ds"]

    # Delete this partition before inserting (idempotent re-run)
    hook.run("DELETE FROM fact_sales WHERE partition_date = %s", parameters=[partition_date])

    FACT_INSERT_SQL = """
    INSERT INTO fact_sales
        (sale_id, customer_key, product_key, region_key, date_key,
         quantity, revenue, cost, profit, partition_date, source)
    SELECT
        CONCAT(s.source, '-', s.customer_id, '-', s.product_id, '-', s.sale_date) AS sale_id,
        dc.customer_key,
        dp.product_key,
        dr.region_key,
        dd.date_key,
        s.quantity::INT,
        s.revenue::NUMERIC,
        dp.cost,
        s.revenue::NUMERIC - dp.cost AS profit,
        %s::DATE AS partition_date,
        s.source
    FROM (
        SELECT customer_id, product_id, region_id, sale_date, quantity, revenue, 's3'  AS source FROM stg_s3_clean
        UNION ALL
        SELECT customer_id, product_id, region_id, sale_date, quantity, revenue, 'oltp' AS source FROM stg_oltp_clean
    ) s
    INNER JOIN dim_customer dc ON dc.customer_id = s.customer_id
    INNER JOIN dim_product  dp ON dp.product_id  = s.product_id
    INNER JOIN dim_region   dr ON dr.region_id   = s.region_id
    INNER JOIN dim_date     dd ON dd.full_date    = s.sale_date::DATE
    WHERE s.sale_date = %s
    ON CONFLICT (sale_id, partition_date) DO NOTHING;
    """
    hook.run(FACT_INSERT_SQL, parameters=[partition_date, partition_date])

    count = hook.get_first(
        "SELECT COUNT(*) FROM fact_sales WHERE partition_date = %s",
        parameters=[partition_date],
    )[0]
    print(f"[INFO] Loaded {count} fact rows for partition {partition_date}")


# ─── Data quality ─────────────────────────────────────────────────────────────

def data_quality_check(**context) -> None:
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)
    partition_date = context["ds"]
    failures = []

    checks = [
        ("dim_customer", "SELECT COUNT(*) FROM dim_customer", None),
        ("dim_product",  "SELECT COUNT(*) FROM dim_product",  None),
        ("dim_date",     "SELECT COUNT(*) FROM dim_date",     None),
        ("dim_region",   "SELECT COUNT(*) FROM dim_region",   None),
        ("fact_sales",   f"SELECT COUNT(*) FROM fact_sales WHERE partition_date = '{partition_date}'", None),
    ]

    print(f"\n{'Table':<20} {'Row Count':>10}  Status")
    print("-" * 45)

    for table, query, _ in checks:
        count = hook.get_first(query)[0]
        status = "OK" if count > 0 else "FAIL"
        print(f"{table:<20} {count:>10}  {status}")
        if count == 0:
            failures.append(f"{table}: 0 rows (partition={partition_date})")

    # Check for null PKs in fact table
    null_count = hook.get_first(
        f"SELECT COUNT(*) FROM fact_sales WHERE sale_id IS NULL AND partition_date = '{partition_date}'"
    )[0]
    if null_count > 0:
        failures.append(f"fact_sales: {null_count} rows with NULL sale_id")

    if failures:
        raise ValueError("Data quality check failed:\n" + "\n".join(failures))

    print("[INFO] All data quality checks passed")


# ─── DAG ──────────────────────────────────────────────────────────────────────

@dag(
    dag_id="data_warehouse_etl",
    default_args=default_args,
    schedule_interval="0 5 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=True,
    tags=["warehouse", "etl", "star-schema"],
)
def data_warehouse_etl_dag():

    with TaskGroup("extract") as extract_group:
        extracted = extract_source.expand(source=["api", "s3", "oltp"])

    with TaskGroup("transform") as transform_group:
        t_api  = PythonOperator(task_id="transform_api",  python_callable=transform_api)
        t_s3   = PythonOperator(task_id="transform_s3",   python_callable=transform_s3)
        t_oltp = PythonOperator(task_id="transform_oltp", python_callable=transform_oltp)

    with TaskGroup("load") as load_group:
        with TaskGroup("dim_loads"):
            d_cust   = PythonOperator(task_id="load_dim_customer", python_callable=load_dim_customer)
            d_prod   = PythonOperator(task_id="load_dim_product",  python_callable=load_dim_product)
            d_date   = PythonOperator(task_id="load_dim_date",     python_callable=load_dim_date)
            d_region = PythonOperator(task_id="load_dim_region",   python_callable=load_dim_region)

        fact_task = PythonOperator(
            task_id="load_fact_sales",
            python_callable=load_fact_sales,
        )

        dq_task = PythonOperator(
            task_id="data_quality_check",
            python_callable=data_quality_check,
        )

        [d_cust, d_prod, d_date, d_region] >> fact_task >> dq_task

    extract_group >> transform_group >> load_group


dag_instance = data_warehouse_etl_dag()
