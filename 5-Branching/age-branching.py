from airflow import DAG
from airflow.operators.python_operator import BranchPythonOperator, PythonOperator
from airflow.operators.dummy_operator import DummyOperator
from datetime import datetime

def get_next_task(age):
    """
    Determine the next task based on the age group.
    """
    if int(age) < 18:
        return 'task_for_below_18'
    elif int(age) > 60:
        return 'task_for_above_60'
    else:
        return 'task_for_between_18_and_60'

def task_for_below_18():
    print("Task for individuals below 18 years old.")

def task_for_above_60():
    print("Task for individuals above 60 years old.")

def task_for_between_18_and_60():
    print("Task for individuals between 18 and 60 years old.")

with DAG('age_group_branching_dag', start_date=datetime(2024, 6, 19)) as dag:
    decision = BranchPythonOperator(
        task_id='get_age_group',
        python_callable=get_next_task,
        op_args=['20'],  
        provide_context=True,
    )
    
    task_below_18 = PythonOperator(
        task_id='task_for_below_18',
        python_callable=task_for_below_18,
    )
    
    task_above_60 = PythonOperator(
        task_id='task_for_above_60',
        python_callable=task_for_above_60,
    )
    
    task_between_18_60 = PythonOperator(
        task_id='task_for_between_18_and_60',
        python_callable=task_for_between_18_and_60,
    )
    
    final_task = DummyOperator(task_id='final_task',trigger_rule='one_success')

    decision >> [task_below_18, task_above_60, task_between_18_60] >> final_task

