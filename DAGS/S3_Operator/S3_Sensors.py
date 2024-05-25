from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

default_args = {
    'owner': 'your_name',
    'retries': 5,
    'retry_delay': timedelta(minutes=5)
}


with DAG(
    dag_id='dag_with_s3key_sensor_v1',
    default_args=default_args,
    start_date=datetime(2021, 12, 19),
    schedule_interval='0 0 * * *'           # For more information: https://crontab.guru/
) as dag:
    
    
    task1=S3KeySensor(
        task_id="sensor_minios_s3",
        bucket_name="minios",
        aws_conn_id="aws_s3_default",
        poke_interval=5
    )
    