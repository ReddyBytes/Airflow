from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 6, 19),
    'email': ['your_email@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'primary_dag',
    default_args=default_args,
    description='Primary DAG to trigger a task in the secondary DAG',
    schedule_interval=timedelta(days=1),
    catchup=False,
)

def trigger_secondary_task():
    print("Triggering task in secondary DAG")

trigger_task = PythonOperator(
    task_id='trigger_secondary_task',
    python_callable=trigger_secondary_task,
    dag=dag,
)

dummy_task = DummyOperator(
    task_id='dummy_task',
    dag=dag,
)

trigger_task >> dummy_task
