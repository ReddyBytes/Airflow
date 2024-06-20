from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.bash_operator import BashOperator

from datetime import datetime

default_args = {
    'start_date': datetime(2019, 1, 1),
    'owner': 'Airflow',
    'email': 'owner@test.com'
}

with DAG(
    dag_id='queue_dag', 
    schedule_interval='0 0 * * *', 
    default_args=default_args, 
    catchup=False
    ) as dag:
    
    t_1_w1 = BashOperator(task_id='t_1_w1', bash_command='echo "I/O intensive task1"', queue='worker_1')

    t_2_w1 = BashOperator(task_id='t_2_w1', bash_command='echo "I/O intensive task2"',  queue='worker_1')

    t_3_w1 = BashOperator(task_id='t_3_w1', bash_command='echo "I/O intensive task3"',  queue='worker_1' )

    t_4_w2 = BashOperator(task_id='t_4_w2', bash_command='echo "instensive task for worker 2_1"',  queue='worker_2')

    t_5_w2 = BashOperator(task_id='t_5_w2', bash_command='echo "instensive task for worker 2_2"', queue='worker_2')

    t_6_w3 = BashOperator(task_id='t_6_w3', bash_command='echo " dependency task"', queue='worker_3')

    task_7 = DummyOperator(task_id='task_7')

    [t_1_w1, t_2_w1, t_3_w1, t_4_w2, t_5_w2, t_6_w3] >> task_7
        