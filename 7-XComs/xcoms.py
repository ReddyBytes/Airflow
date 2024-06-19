from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.models import Variable

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 6, 19),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'xcom_example',
    default_args=default_args,
    description='Example DAG to demonstrate XComs',
    schedule_interval=timedelta(days=1),
    catchup=False,
    ) as dag:

    def push_to_xcom(**context):
        context['ti'].xcom_push(key='example_key', value='example_data')

    def pull_from_xcom(**context):
        data = context['ti'].xcom_pull(key='example_key', task_ids='push_to_xcom_task')
        print(f"Pulled data: {data}")

    push_task = PythonOperator(
    task_id='push_to_xcom_task',
    python_callable=push_to_xcom,
    dag=dag,
    )

    pull_task = PythonOperator(
        task_id='pull_from_xcom_task',
        python_callable=pull_from_xcom,
        dag=dag,
    )

    push_task >> pull_task
