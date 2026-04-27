"""
Project 10 — Airflow on Kubernetes
Complete Solution DAG with KubernetesPodOperator

Each task runs in an isolated Kubernetes pod with its own container image.
Shared data is passed via a shared EmptyDir volume (simple approach for local dev).
For production, use S3 XCom backend or a PVC.

Reference: Helm values.yaml is at the bottom of this file as a comment block.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from kubernetes.client import models as k8s

default_args = {
    "owner": "platform-eng",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": False,
}

# ─── Shared volume (EmptyDir — lives for the duration of the pod lifecycle) ──
# For production, replace with a PVC that persists across pods.
# All 3 tasks share /shared via the same volume name — but wait:
# EmptyDir is per-pod, so tasks cannot share it directly via KubernetesPodOperator
# (each task is a separate pod). Use the PVC approach below for real inter-task data.
#
# For this solution, each task writes its output to Postgres instead of a shared file,
# making the pipeline truly stateless between tasks.

shared_volume = k8s.V1Volume(
    name="shared-data",
    empty_dir=k8s.V1EmptyDirVolumeSource(),  # ← in-pod tmp storage
)

shared_mount = k8s.V1VolumeMount(
    name="shared-data",
    mount_path="/shared",
)

resource_limits = k8s.V1ResourceRequirements(
    limits={"memory": "512Mi",  "cpu": "500m"},
    requests={"memory": "256Mi", "cpu": "200m"},
)

# ─── Extract task ─────────────────────────────────────────────────────────────

EXTRACT_CMD = """
pip install requests psycopg2-binary --quiet && python3 -c "
import requests
import json
import psycopg2
import os

# Fetch data from public API
resp = requests.get('https://fakestoreapi.com/products', timeout=30)
resp.raise_for_status()
products = resp.json()
print(f'[EXTRACT] Fetched {len(products)} products from API')

# Write to Postgres staging table (avoids shared-volume cross-pod problem)
conn = psycopg2.connect(
    host=os.environ['PGHOST'],
    port=os.environ.get('PGPORT', '5432'),
    user=os.environ['PGUSER'],
    password=os.environ['PGPASSWORD'],
    dbname=os.environ['PGDATABASE'],
)
with conn.cursor() as cur:
    cur.execute('''
        CREATE TABLE IF NOT EXISTS k8s_raw_products (
            id INT, title TEXT, price FLOAT, category TEXT,
            loaded_at TIMESTAMP DEFAULT NOW()
        );
        TRUNCATE k8s_raw_products;
    ''')
    for p in products:
        cur.execute(
            'INSERT INTO k8s_raw_products (id, title, price, category) VALUES (%s,%s,%s,%s)',
            (p['id'], p['title'], p['price'], p['category'])
        )
conn.commit()
conn.close()
print(f'[EXTRACT] Wrote {len(products)} rows to k8s_raw_products')
"
"""

# ─── Transform task ───────────────────────────────────────────────────────────

TRANSFORM_CMD = """
pip install pandas psycopg2-binary --quiet && python3 -c "
import pandas as pd
import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ['PGHOST'],
    port=os.environ.get('PGPORT', '5432'),
    user=os.environ['PGUSER'],
    password=os.environ['PGPASSWORD'],
    dbname=os.environ['PGDATABASE'],
)

df = pd.read_sql('SELECT * FROM k8s_raw_products', conn)
print(f'[TRANSFORM] Read {len(df)} rows from k8s_raw_products')

summary = (
    df.groupby('category')
    .agg(
        product_count=('id', 'count'),
        avg_price=('price', 'mean'),
        min_price=('price', 'min'),
        max_price=('price', 'max'),
    )
    .reset_index()
    .round(2)
)
print('[TRANSFORM] Category summary:')
print(summary.to_string())

with conn.cursor() as cur:
    cur.execute('''
        CREATE TABLE IF NOT EXISTS k8s_category_summary (
            category TEXT UNIQUE,
            product_count INT,
            avg_price FLOAT,
            min_price FLOAT,
            max_price FLOAT,
            transformed_at TIMESTAMP DEFAULT NOW()
        );
        TRUNCATE k8s_category_summary;
    ''')
    for _, row in summary.iterrows():
        cur.execute(
            '''INSERT INTO k8s_category_summary
               (category, product_count, avg_price, min_price, max_price)
               VALUES (%s, %s, %s, %s, %s)''',
            (row['category'], row['product_count'], row['avg_price'],
             row['min_price'], row['max_price'])
        )
conn.commit()
conn.close()
print(f'[TRANSFORM] Wrote {len(summary)} rows to k8s_category_summary')
"
"""

# ─── Load task ────────────────────────────────────────────────────────────────

LOAD_CMD = """
pip install psycopg2-binary --quiet && python3 -c "
import psycopg2
import os
from datetime import datetime

conn = psycopg2.connect(
    host=os.environ['PGHOST'],
    port=os.environ.get('PGPORT', '5432'),
    user=os.environ['PGUSER'],
    password=os.environ['PGPASSWORD'],
    dbname=os.environ['PGDATABASE'],
)

with conn.cursor() as cur:
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pipeline_output (
            run_date DATE,
            category TEXT,
            product_count INT,
            avg_price FLOAT,
            min_price FLOAT,
            max_price FLOAT,
            loaded_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (run_date, category)
        );
    ''')
    # Read from transform output and write to final output table
    cur.execute('SELECT category, product_count, avg_price, min_price, max_price FROM k8s_category_summary')
    rows = cur.fetchall()
    today = datetime.now().date()

    for row in rows:
        cur.execute('''
            INSERT INTO pipeline_output
                (run_date, category, product_count, avg_price, min_price, max_price)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_date, category) DO UPDATE SET
                product_count = EXCLUDED.product_count,
                avg_price     = EXCLUDED.avg_price,
                loaded_at     = NOW();
        ''', (today,) + row)

conn.commit()

with conn.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM pipeline_output')
    total = cur.fetchone()[0]

conn.close()
print(f'[LOAD] pipeline_output now has {total} rows total')
"
"""

# ─── DB env vars (reads from Kubernetes Secret 'airflow-db-secret') ──────────

DB_ENV_VARS = [
    k8s.V1EnvVar(
        name="PGHOST",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name="airflow-db-secret",
                key="host",
                optional=True,                  # ← optional so DAG loads without secret
            )
        ),
    ),
    k8s.V1EnvVar(
        name="PGUSER",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name="airflow-db-secret",
                key="username",
                optional=True,
            )
        ),
    ),
    k8s.V1EnvVar(
        name="PGPASSWORD",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name="airflow-db-secret",
                key="password",
                optional=True,
            )
        ),
    ),
    k8s.V1EnvVar(name="PGDATABASE", value="airflow"),
    k8s.V1EnvVar(name="PGPORT",     value="5432"),
]

# ─── DAG ──────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="k8s_pipeline_dag",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kubernetes", "k8s", "capstone"],
    doc_md="""
    ## K8s Pipeline DAG
    Runs 3 tasks in isolated Kubernetes pods:
    - extract: python:3.12-slim (API fetch → Postgres staging)
    - transform: python:3.12-slim + pandas (aggregate → Postgres)
    - load: python:3.12-slim (staging → pipeline_output table)
    """,
) as dag:

    extract = KubernetesPodOperator(
        task_id="extract",
        image="python:3.12-slim",
        name="k8s-pipeline-extract",
        namespace="airflow",
        cmds=["bash", "-c"],
        arguments=[EXTRACT_CMD],
        env_vars=DB_ENV_VARS,
        volume_mounts=[shared_mount],
        volumes=[shared_volume],
        container_resources=resource_limits,
        is_delete_operator_pod=True,            # ← clean up pod on success
        get_logs=True,                          # ← stream pod logs to Airflow task logs
        in_cluster=True,
        service_account_name="airflow-scheduler",
    )

    transform = KubernetesPodOperator(
        task_id="transform",
        image="python:3.12-slim",               # ← same image; pandas installed at runtime
        name="k8s-pipeline-transform",          # ← in prod, use pre-built image with pandas
        namespace="airflow",
        cmds=["bash", "-c"],
        arguments=[TRANSFORM_CMD],
        env_vars=DB_ENV_VARS,
        volume_mounts=[shared_mount],
        volumes=[shared_volume],
        container_resources=resource_limits,
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        service_account_name="airflow-scheduler",
    )

    load = KubernetesPodOperator(
        task_id="load",
        image="python:3.12-slim",
        name="k8s-pipeline-load",
        namespace="airflow",
        cmds=["bash", "-c"],
        arguments=[LOAD_CMD],
        env_vars=DB_ENV_VARS,
        volume_mounts=[shared_mount],
        volumes=[shared_volume],
        container_resources=resource_limits,
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        service_account_name="airflow-scheduler",
    )

    extract >> transform >> load


# ─── HELM VALUES.YAML REFERENCE ──────────────────────────────────────────────
# Save this as values.yaml and use with: helm install airflow apache-airflow/airflow \
#   --namespace airflow --values values.yaml --wait
#
# executor: "KubernetesExecutor"
#
# webserver:
#   replicas: 1
#   service:
#     type: NodePort
#     nodePort: 30080
#   defaultUser:
#     enabled: true
#     role: Admin
#     username: admin
#     email: admin@example.com
#     firstName: Admin
#     lastName: User
#     password: admin
#
# scheduler:
#   replicas: 1
#   serviceAccount:
#     create: false
#     name: airflow-scheduler
#
# config:
#   core:
#     executor: KubernetesExecutor
#     dags_are_paused_at_creation: "false"
#   kubernetes:
#     namespace: airflow
#     worker_container_repository: apache/airflow
#     worker_container_tag: "2.8.0"
#     delete_worker_pods: "True"
#     delete_worker_pods_on_failure: "False"
#     worker_pods_creation_batch_size: "4"
#
# dags:
#   persistence:
#     enabled: true
#     size: 1Gi
#     accessMode: ReadWriteMany
#     storageClassName: standard
#
# logs:
#   persistence:
#     enabled: true
#     size: 5Gi
#     storageClassName: standard
#
# postgresql:
#   enabled: true
#   auth:
#     username: airflow
#     password: airflow
#     database: airflow
