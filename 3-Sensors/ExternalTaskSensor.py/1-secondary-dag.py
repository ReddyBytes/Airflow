from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.sensors.external_task_sensor import ExternalTaskSensor
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 6, 19),
    'email': ['your_email@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
    }

dag = DAG(
    'secondary_dag',
    default_args=default_args,
    description='Secondary DAG with a task waiting for a task from the primary DAG',
    schedule_interval=timedelta(days=1),
    catchup=False
)

wait_for_primary_task = ExternalTaskSensor(
    task_id='wait_for_primary_task',
    external_dag_id='primary_dag',
    external_task_id='trigger_secondary_task',
    dag=dag,
)

dummy_task = DummyOperator(
    task_id='dummy_task',
    dag=dag,
)

wait_for_primary_task >> dummy_task
