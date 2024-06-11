from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.operators.s3 import S3UploadFileOperator

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 5, 15),
    'email': ['your_email@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2),
}

dag = DAG(
    dag_id='upload_to_s3', 
    default_args=default_args, 
    description='Upload a file to an S3 bucket using S3UploadFileOperator',
    schedule_interval=timedelta(days=1),
    catchup=False
)

upload_file_task = S3UploadFileOperator(
    task_id='upload_file_into_S3',
    aws_conn_id='aws_default',  #This name should match the connection ID for AWS credentials
    bucket_name='my-bucket-name',
    bucket_key='my-file.txt', 
   # object_name='local/path/to/my-file.txt',  
    
)

upload_file_task
