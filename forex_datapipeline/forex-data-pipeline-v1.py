from airflow import DAG
from datetime import datetime, timedelta
from airflow.providers.http.sensors.http import HttpSensor

default_args={
    "owner":"ReddyBytes",
    "depends_on_past":False,
    "email":"your_email@example.com",
    "email_on_failure":False,
    "email_on_retry":False,
    "catchup":False,
    "retries":5,
    "retry_delay":timedelta(minutes=5)
}

with DAG(
    dag_id="forex_data_pipeline_v1",
    default_args=default_args,
    start_date=datetime(2021, 1, 1),
    schedule_interval="@daily",
    catchup=False
    ) as dag:

    forex_data_check=HttpSensor(
        task_id="forex_data_check",
        http_conn_id="http_conn_id",
        endpoint="/forex_data.csv",
        method="GET",
        response_check=lambda response: response.status_code == 200,
        poke_interval=60,
        timeout=600,
        retries=5,
        retry_delay=timedelta(minutes=5)
    
    )