from datetime import datetime, timedelta
from airflow import DAG
import pandas as pd
import boto3
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.python_operator import PythonOperator
from airflow.providers.amazon.aws.transfers.local_to_s3 import LocalFilesystemToS3Operator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

default_args = {
    'owner': 'your_name',
    'retries': 5,
    'retry_delay': timedelta(minutes=5)
}


with DAG(
    dag_id='Create_Insert_Read_Manipulate_Write_Upload_DAG',
    description='creating a table and inserting data into it. Manipulate the data in the table and Write the manipulated data to a CSV file.Upload the CSV file to S3.',
    default_args=default_args,
    start_date=datetime(2021, 12, 19),
    schedule_interval='0 0 * * *'           # For more information: https://crontab.guru/
) as dag:
    
        
    create_table_task = PostgresOperator(
        task_id='create_table',
        postgres_conn_id='postgres_localhost',  # Make sure this connection ID matches one in your Airflow connections
        sql="""
            CREATE TABLE IF NOT EXISTS Training (
                id SERIAL PRIMARY KEY,
                name VARCHAR(30),
                location VARCHAR(100),
                age INTEGER
            );
        """,
        dag=dag,
    )

    insert_data_into_table = PostgresOperator(
        task_id='insert__data_into_table',
        postgres_conn_id='postgres_localhost',
        sql="""
            INSERT INTO Training (name, location, age) VALUES
            ('Penchalareddy', 'Hyderabad', 24),
            ('Syam Kumar', 'Los Angeles', 23),
            ('Sushrut Vaidya', 'Nagpur', 22),
            ('Manish', 'Delhi', 40),
            ('Jarnail', 'US', 36),
            ('Tiru', 'New York', 32);
        """,
        dag=dag,
    
    )

    export_data_into_file=PostgresOperator(
        task_id='export_data_into_file',
        postgres_conn_id='postgres_localhost',
        sql="""
            COPY dag_runs TO '/tmp/Training.csv' DELIMITER ',' CSV HEADER;
        """
    )
    
    # def manipulate_data_from_file():
    #     df = pd.read_csv('/tmp/Training.csv')
    #     df['age'] += 5
    #     df.to_csv('/tmp/Manipulated_Training_data.csv', index=False)
    #     # print(df.head())
    
    def manipulate_data_from_file():
        source='/tmp/Training.csv'
        destination='/tmp/Manipulated_Training_data.csv'
        with open(source, 'r') as source_file:
            content=source_file.read()
        manipulate_data=content.replace('age', 'age+5')
        with open(destination, 'w') as destination_file:
            destination_file.write(manipulate_data)
            
        print('Manipulated data is written to file')
    
    read_data_from_file_and_manipulate_data_and_write_to_file = PythonOperator(
        task_id='read_manipulate_write_data_to_file',
        python_callable=manipulate_data_from_file,
        dag=dag,
    )
    
    
        
    local_to_s3 = LocalFilesystemToS3Operator(
        task_id='local_to_s3',
        filename='/tmp/Manipulated_Training_data.csv',
        dest_key='s3://s3_bucket/Manipulated_Training_data.csv',
        #dest_bucket='s3_bucket',
        aws_conn_id='aws_default',
        
    )
    
    # final_result=S3KeySensor(
    #     task_id="Results_that_file_is_uploaded_to_s3",
    #     bucket_name="plreddy_s3_bucket",
    #     bucket_key='Manipulated_Training_data.csv',
    #     aws_conn_id="aws_default",
    #     mode='poke',
    #     poke_interval=5,
    #     timeout=30
    # )
    
    def check_file_in_s3_and_log_message():
        s3_client = boto3.client('s3', region_name='us-east-1')  # Specify your AWS region
        bucket_name = 'plreddy_s3_bucket'
        key = 'Manipulated_Training_data.csv'
        
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            print("The file 'Manipulated_Training_data.csv' has been uploaded successfully.")
        except Exception as e: 
            print(f"The file 'Manipulated_Training_data.csv' does not exist in S3. Error: {e}")

    log_message_task = PythonOperator(
        task_id='log_message_after_file_upload',
        python_callable=check_file_in_s3_and_log_message,
        dag=dag,
    )
    create_table_task >> insert_data_into_table >> export_data_into_file >> read_data_from_file_and_manipulate_data_and_write_to_file >> upload_file_to_S3 >> final_result >> log_message_task


    

    
    
    