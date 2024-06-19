import sys
import airflow
from airflow import DAG, macros
from airflow.operators.bash_operator import BashOperator
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
        bash_command="echo {{ ts_nodash }} - {{ macros.ds_format(ts_nodash, '%Y%m%dT%H%M%S', '%Y-%m-%d-%H-%M') }}")