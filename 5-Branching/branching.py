from airflow import DAG
from airflow.operators.python_operator import BranchPythonOperator,PythonOperator
from datetime import datetime

def pick_toys():
    print("Picking up toys...")

def sort_clothes():
    print("Sorting clothes...")

def decide_what_to_do():
    if True:  
        return 'pick_toys'
    else:
        return 'sort_clothes'

with DAG('branching_example', start_date=datetime(2024, 6, 19)) as dag:
    decision = BranchPythonOperator(
        task_id='decide_what_to_do',
        python_callable=decide_what_to_do,
        provide_context=True,
    )
    
    pick_toys_task = PythonOperator(
        task_id='pick_toys',
        python_callable=pick_toys,
    )
    
    sort_clothes_task = PythonOperator(
        task_id='sort_clothes',
        python_callable=sort_clothes,
    )
    
    decision >> pick_toys_task | sort_clothes_task
