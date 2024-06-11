from airflow.operators.python_operator import PythonOperator
import csv
import psycopg2

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator

def export_to_csv(**context):
    # Establish a connection to the PostgreSQL database
    conn = psycopg2.connect(database="your_database", user="your_username", password="your_password", host="your_host", port="5432")
    cur = conn.cursor()
    
    # Execute a SELECT statement to fetch data from the table
    cur.execute("SELECT * FROM dag_runs;")
    rows = cur.fetchall()
    
    # Open a CSV file and write the fetched data to it
    with open('/path/to/dag_runs.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        
        # Write the header row
        writer.writerow([column[0] for column in cur.description])
        
        # Write the data rows
        writer.writerows(rows)
    
    # Close the cursor and connection
    cur.close()
    conn.close()
    


default_args = {
    'owner': 'your_name',
    'retries': 5,
    'retry_delay': timedelta(minutes=5)
}


with DAG(
    dag_id='dag_with_postgres_operator_v1',
    default_args=default_args,
    start_date=datetime(2021, 12, 19),
    schedule_interval='0 0 * * *'           # For more information: https://crontab.guru/
) as dag:

    export_task = PythonOperator(
        task_id='export_table_to_csv',
        python_callable=export_to_csv,
        dag=dag,
    )

    export_task