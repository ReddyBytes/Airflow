# 07 — Connections and Hooks: Code Examples

## Example 1 — PostgresHook: Query a Database

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime

def query_users():
    # conn_id must match a Connection record named "my_postgres"
    hook = PostgresHook(postgres_conn_id="my_postgres")

    # get_records returns a list of tuples
    records = hook.get_records("SELECT id, email FROM users WHERE active = TRUE LIMIT 5")
    for row in records:
        print(f"User {row[0]}: {row[1]}")

    # run() executes INSERT/UPDATE/DELETE
    hook.run("UPDATE users SET last_seen = NOW() WHERE id = 1")

    # get_pandas_df returns a DataFrame
    df = hook.get_pandas_df("SELECT * FROM orders WHERE status = 'pending'")
    print(df.head())

with DAG(
    dag_id="postgres_hook_demo",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    query_task = PythonOperator(
        task_id="query_users",
        python_callable=query_users,
    )
```

---

## Example 2 — S3Hook: List Files in a Bucket

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from datetime import datetime

def list_s3_files():
    # aws_conn_id must match a Connection of type "aws"
    hook = S3Hook(aws_conn_id="my_aws")

    # List all keys with a given prefix
    keys = hook.list_keys(bucket_name="my-data-bucket", prefix="raw/2024/")
    print(f"Found {len(keys)} files:")
    for key in keys:
        print(f"  s3://my-data-bucket/{key}")

    # Check if a specific object exists
    exists = hook.check_for_key("raw/2024/01/data.csv", bucket_name="my-data-bucket")
    print(f"data.csv exists: {exists}")

    # Download a file to local disk
    hook.download_file(
        key="raw/2024/01/data.csv",
        bucket_name="my-data-bucket",
        local_path="/tmp/data.csv",
    )

with DAG(
    dag_id="s3_hook_demo",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    list_task = PythonOperator(
        task_id="list_s3_files",
        python_callable=list_s3_files,
    )
```

---

## Example 3 — HttpHook: Call a REST API

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.http.hooks.http import HttpHook
from datetime import datetime
import json

def call_api():
    # http_conn_id must be a Connection of type "http"
    # The Connection's "host" field should be the base URL, e.g. https://api.example.com
    hook = HttpHook(method="GET", http_conn_id="my_api")

    # GET request — endpoint is appended to the base URL from the Connection
    response = hook.run(
        endpoint="/v1/products",
        headers={"Accept": "application/json", "Authorization": "Bearer mytoken"},
        extra_options={"timeout": 30},
    )
    products = response.json()
    print(f"Received {len(products)} products")

    # POST request
    post_hook = HttpHook(method="POST", http_conn_id="my_api")
    post_response = post_hook.run(
        endpoint="/v1/events",
        data=json.dumps({"event": "dag_completed", "dag_id": "http_demo"}),
        headers={"Content-Type": "application/json"},
    )
    print(f"POST status: {post_response.status_code}")

with DAG(
    dag_id="http_hook_demo",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    api_task = PythonOperator(
        task_id="call_api",
        python_callable=call_api,
    )
```

---

## Example 4 — Setting a Connection via Environment Variable

No Python code needed — set the variable before starting Airflow (in your shell, Docker Compose `.env`, or Kubernetes secret).

```bash
# Postgres
export AIRFLOW_CONN_MY_POSTGRES="postgresql://airflow_user:s3cr3t@postgres-host:5432/mydb"

# HTTP API (base URL goes in the host field; encode "://" as %3A%2F%2F in some shells)
export AIRFLOW_CONN_MY_API="http://https%3A%2F%2Fapi.example.com"

# AWS (key in login, secret in password, region in extra via query string)
export AIRFLOW_CONN_MY_AWS="aws://AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI%2FK7MDENG%2FbPxRfiCYEXAMPLEKEY@/?region_name=us-east-1"
```

Verify Airflow can see it:

```bash
airflow connections get my_postgres
# Output:
# Id: my_postgres
# Connection Type: postgres
# Host: postgres-host
# Schema: mydb
# Login: airflow_user
# Password: s3cr3t
# Port: 5432
```

Then reference it in your DAG exactly as before — the `conn_id` string is all your code ever needs:

```python
hook = PostgresHook(postgres_conn_id="my_postgres")  # reads from env var automatically
```
