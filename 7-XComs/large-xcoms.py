import boto3
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta

s3_client = boto3.client('s3')

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
    'large_data_transfer',
    default_args=default_args,
    description='Example DAG for large data transfer',
    schedule_interval=timedelta(days=1),
    catchup=False,
)

def upload_large_data_to_s3(**kwargs):
    bucket_name = 'your-bucket-name'
    object_key = 'path/to/large/data.txt'
    
    s3_client.upload_file(Filename='local_file_path', Bucket=bucket_name, Key=object_key)
    
    kwargs['ti'].xcom_push(key='data_uri', value=f"s3://{bucket_name}/{object_key}")

def download_large_data_from_s3(**kwargs):
    bucket_name = 'your-bucket-name'
    object_key = kwargs['ti'].xcom_pull(key='object_key')
    
    s3_client.download_file(Bucket=bucket_name, Key=object_key, Filename='downloaded_data.txt')
    
    print("Large data downloaded successfully.")

upload_task = PythonOperator(
    task_id='upload_large_data_to_s3',
    python_callable=upload_large_data_to_s3,
    provide_context=True,
    dag=dag,
)

download_task = PythonOperator(
    task_id='download_large_data_from_s3',
    python_callable=download_large_data_from_s3,
    provide_context=True,
    dag=dag,
)

upload_task >> download_task
