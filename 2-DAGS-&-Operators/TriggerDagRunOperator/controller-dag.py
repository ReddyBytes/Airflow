from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
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
    'controller_dag',
    default_args=default_args,
    description='Controller DAG to conditionally trigger target DAG',
    schedule_interval=timedelta(days=1),
    catchup=False,
)

def evaluate_conditions(**kwargs):
    if datetime.now().weekday() < 5:
        return True 
    else:
        return False  

evaluate_condition_task = PythonOperator(
    task_id='evaluate_conditions',
    python_callable=evaluate_conditions,
    provide_context=True,
    dag=dag,
)

task_1 = DummyOperator(task_id='task_1', dag=dag)

trigger_target_dag = TriggerDagRunOperator(
    task_id='trigger_target_dag',
    trigger_dag_id='target_dag',
    dag=dag,
    dag_run_conf_id='condition_met'
)

evaluate_condition_task >> task_1 >> trigger_target_dag
