"""
Project 09 — Multi-Source Data Warehouse ETL
DAG Starter: TaskGroup structure defined, tasks as stubs.
"""

from airflow.decorators import dag, task
from airflow.utils.task_group import TaskGroup
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

# TODO: Import PostgresHook
# TODO: Import requests (for API extract)
# TODO: Import pandas

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# ─── Extract ──────────────────────────────────────────────────────────────────

@task
def extract_source(source: str, **context) -> str:
    """
    TODO: Handle 3 cases based on source parameter:

    Case "api":
        - Call REST API (fakestoreapi.com or your mock)
        - Write raw JSON rows to stg_api_raw using PostgresHook
        - Return "stg_api_raw"

    Case "s3":
        - Read CSV from S3 using boto3 or s3fs
        - Write rows to stg_s3_raw using PostgresHook
        - Return "stg_s3_raw"

    Case "oltp":
        - Query Postgres OLTP source using PostgresHook("postgres_oltp")
        - Write rows to stg_oltp_raw using PostgresHook("postgres_warehouse")
        - Return "stg_oltp_raw"
    """
    # TODO: implement
    raise NotImplementedError(f"extract_source not implemented for source={source}")


# ─── Transform ────────────────────────────────────────────────────────────────

def transform_api(**context) -> None:
    """
    TODO:
    - Read stg_api_raw
    - Standardize column names to warehouse conventions
    - Fill nulls, cast types
    - Write to stg_api_clean
    """
    pass


def transform_s3(**context) -> None:
    """
    TODO: Same as transform_api but for stg_s3_raw → stg_s3_clean
    Pay attention to date format differences (API uses ISO, CSV often uses MM/DD/YYYY)
    """
    pass


def transform_oltp(**context) -> None:
    """
    TODO: Same as transform_api but for stg_oltp_raw → stg_oltp_clean
    The OLTP source may have different ID formats — normalize them here
    """
    pass


# ─── Dimension loads ──────────────────────────────────────────────────────────

def load_dim_customer(**context) -> None:
    """
    TODO:
    - Read customer data from all 3 clean staging tables (UNION)
    - Deduplicate by customer_id (keep most recent)
    - SCD Type 1 upsert into dim_customer:
      INSERT ... ON CONFLICT (customer_id) DO UPDATE SET name=EXCLUDED.name, ...
    """
    pass


def load_dim_product(**context) -> None:
    """TODO: SCD1 upsert from stg_*_clean into dim_product"""
    pass


def load_dim_date(**context) -> None:
    """
    TODO: Generate date dimension rows for all dates in the partition range.
    Hint: pandas date_range + .dt accessor for year/month/quarter/week/is_weekend
    SCD1 upsert into dim_date ON CONFLICT (full_date) DO UPDATE SET ...
    """
    pass


def load_dim_region(**context) -> None:
    """TODO: SCD1 upsert from stg_*_clean into dim_region"""
    pass


# ─── Fact table load ──────────────────────────────────────────────────────────

def load_fact_sales(**context) -> None:
    """
    TODO:
    1. DELETE FROM fact_sales WHERE partition_date = context["ds"]
    2. INSERT ... SELECT ... with 4 JOINs to resolve dimension keys
       - INNER JOIN dim_customer ON customer_id
       - INNER JOIN dim_product  ON product_id
       - INNER JOIN dim_region   ON region_id
       - INNER JOIN dim_date     ON full_date = sale_date
    3. Log count of inserted rows
    4. Log count of dropped rows (unresolvable FK) as warnings
    """
    pass


# ─── Data quality check ───────────────────────────────────────────────────────

def data_quality_check(**context) -> None:
    """
    TODO:
    For each warehouse table [dim_customer, dim_product, dim_date, dim_region, fact_sales]:
        - Assert COUNT(*) > 0
        - Assert no null primary keys

    Raise ValueError with descriptive message on any failure.
    Log all results in a structured table format.
    """
    pass


# ─── DAG ─────────────────────────────────────────────────────────────────────

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
        # TODO: Use extract_source.expand(source=["api", "s3", "oltp"])
        extracted = None  # replace with extract_source.expand(...)

    with TaskGroup("transform") as transform_group:
        t_api  = PythonOperator(task_id="transform_api",  python_callable=transform_api)
        t_s3   = PythonOperator(task_id="transform_s3",   python_callable=transform_s3)
        t_oltp = PythonOperator(task_id="transform_oltp", python_callable=transform_oltp)

    with TaskGroup("load") as load_group:
        with TaskGroup("dim_loads") as dim_loads_group:
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

        # Dimension loads run in parallel, fact loads after all dims
        [d_cust, d_prod, d_date, d_region] >> fact_task >> dq_task

    # TODO: Wire groups together
    # extract_group >> transform_group >> load_group


dag_instance = data_warehouse_etl_dag()
