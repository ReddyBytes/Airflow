import sys
import airflow
from airflow import DAG, macros
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.postgres_operator import PostgresOperator
from datetime import datetime, timedelta


default_args = {
            "owner": "Airflow",
            "start_date": airflow.utils.dates.days_ago(1),
            "depends_on_past": False,
            "email_on_failure": False,
            "email_on_retry": False,
            "email": "youremail@host.com",
            "retries": 1
        }

with DAG(
    dag_id="template_dag", 
    schedule_interval="@daily", 
    default_args=default_args
    ) as dag:

    t0 = BashOperator(
        task_id="t0",
        bash_command="echo {{ ds }}")
    
    t1 = BashOperator(
            task_id="t1",
            bash_command="echo {{var.value.VARIABLE_KEY}}")

    

    #t0 >> t1 