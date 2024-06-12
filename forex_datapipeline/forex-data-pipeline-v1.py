from airflow import DAG
from datetime import datetime, timedelta
from airflow.providers.http.sensors.http import HttpSensor
from airflow.sensors.filesystem import FileSensor


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
        endpoint="ReddyBytes/Airflow/blob/main/forex_datapipeline/api-forex-exchange.json",
        method="GET",
        response_check=lambda response: "rates" in response.text,
        poke_interval=60,
        timeout=600,
    )

    file_check=FileSensor(
        task_id="file checking in the path",
        file_conn_id="forex_path",
        filepath='file_name',   # /opt/airflow/files/test.csv  then filepath =test.csv ,  connections extras ={/opt/airflow/files} 
        poke_interval=60,
        timeout=600

    )