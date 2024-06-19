from airflow import DAG
from datetime import datetime,timedelta
from airflow.sensors.filesystem import FileSensor
from airflow.operators.dummy_operator import DummyOperator


default_args={
        "owner":"ReddyBytes",
        "email":"youremail@gmail.com",
        "email_on_failure":False,
        "email_on_retry":False,
        "retries":3,
        "retry_delay":timedelta(minutes=5)
}


with DAG(
    dag_id="file_sensor_dag_v2",
    default_args=default_args,
    start_date=datetime(2024,6,10),
    schedule_interval="@daily",
    catchup=False
    ) as dag:

    start = DummyOperator(task_id='start', dag=dag)
    end = DummyOperator(task_id='end', dag=dag)


    file_sensor = FileSensor(
        task_id='wait_for_file',
        filepath='/opt/files/test.txt',
        fs_conn_id='file_conn',
        dag=dag,
    )


    start >> file_sensor >> end
