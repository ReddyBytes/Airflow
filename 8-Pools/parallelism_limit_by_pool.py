from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def task_one():
    print("Executing Task One")

def task_two():
    print("Executing Task Two")

def task_three():
    print("Executing Task Three")

with DAG(
    dag_id='pool_limit_example',
    default_args=default_args,
    description='Demonstrating pool parallelism limitation',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 6, 20),
    catchup=False,
    ) as dag:

    task_one = PythonOperator(
        task_id='task_one',
        python_callable=task_one,
        pool='test-client',
        priority_weight=1
   
    )

    task_two = PythonOperator(
        task_id='task_two',
        python_callable=task_two,
        pool='test-client',
        priority_weight=2
    
    )

    task_three = PythonOperator(
        task_id='task_three',
        python_callable=task_three,
        pool='test-client',
        priority_weight=3
        
    )

  
    task_one >> task_two >> task_three
