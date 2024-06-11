from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.operators.s3 import S3CreateBucketOperator

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 5, 15),
    'catchup': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2),
}

dag = DAG(
    dag_id='create_s3_bucket', 
    default_args=default_args, 
    description='S3 bucket creation using S3CreateBucketOperator',
    schedule_interval=timedelta(days=1),
)

create_bucket_task = S3CreateBucketOperator(
    task_id='create_s3_bucket',
    bucket_name='my-new-bucket-name',
    region_name='N-Virginia',
    conn_id='aws_default',  
    dag=dag,
)

create_bucket_task
