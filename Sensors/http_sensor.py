from datetime import timedelta
from airflow import DAG
from airflow.sensors.http_sensor import HttpSensor
from airflow.operators.dummy_operator import DummyOperator
from airflow.utils.dates import days_ago

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='http_sensor_example_v1',
    default_args=default_args,
    description='An example DAG using HttpSensor',
    schedule_interval=timedelta(days=1),
    start_date=days_ago(2),
    ) as dag:

    start = DummyOperator(task_id='start', dag=dag)
    end = DummyOperator(task_id='end', dag=dag)


    http_sensor = HttpSensor(
        task_id='wait_for_http_success',
        http_conn_id='http_conn',
        endpoint="ReddyBytes/Airflow/blob/main/forex_datapipeline/api-forex-exchange.json",
        method="GET",
        response_check=lambda response: "rates" in response.text,
        poke_interval=60,
        timeout=500
        )


    start >> http_sensor >> end