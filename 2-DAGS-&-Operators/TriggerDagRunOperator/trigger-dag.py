from airflow import DAG
from airflow.operators.bash_operator import BashOperator
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
    'target_dag',
    default_args=default_args,
    description='Target DAG to be triggered by the controller',
    schedule_interval=timedelta(days=1),
    catchup=False,
)

task_1 = BashOperator(
    task_id='task_1',
    bash_command='echo "Task 1 completed"',
    dag=dag,
)

task_2 = BashOperator(
    task_id='task_2',
    bash_command='echo "Task 2 completed"',
    dag=dag,
)

task_1 >> task_2 
