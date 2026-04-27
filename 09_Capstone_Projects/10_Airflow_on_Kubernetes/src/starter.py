"""
Project 10 — Airflow on Kubernetes
DAG Starter: KubernetesPodOperator tasks defined with TODOs.
"""

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from datetime import datetime, timedelta
from kubernetes.client import models as k8s

# TODO: Import V1EnvVar, V1ResourceRequirements, V1VolumeMount, V1Volume
# from kubernetes.client import models as k8s

default_args = {
    "owner": "platform-eng",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="k8s_pipeline_dag",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kubernetes", "k8s", "capstone"],
) as dag:

    # ── Task 1: Extract ──────────────────────────────────────────────────────
    extract = KubernetesPodOperator(
        task_id="extract",
        # TODO: Set image to "python:3.12-slim"
        image=None,
        # TODO: Set name (pod name prefix) to "k8s-pipeline-extract"
        name=None,
        # TODO: Set namespace to "airflow"
        namespace=None,
        # TODO: Set cmds and arguments to run:
        #   pip install requests && python -c "
        #     import requests, json, os
        #     data = requests.get('https://fakestoreapi.com/products?limit=5').json()
        #     with open('/shared/raw.json', 'w') as f: json.dump(data, f)
        #     print(f'Extracted {len(data)} products')
        #   "
        cmds=None,
        arguments=None,
        # TODO: Mount a shared volume at /shared
        # volume_mounts=[k8s.V1VolumeMount(name="shared-data", mount_path="/shared")]
        volume_mounts=None,
        volumes=None,
        # TODO: Set env_vars with any needed environment variables
        env_vars=None,
        # TODO: Set resource limits
        # container_resources=k8s.V1ResourceRequirements(
        #     limits={"memory": "256Mi", "cpu": "250m"},
        #     requests={"memory": "128Mi", "cpu": "100m"},
        # )
        container_resources=None,
        # TODO: Set is_delete_operator_pod=True to clean up after completion
        is_delete_operator_pod=False,
        # TODO: Set get_logs=True to stream logs to Airflow
        get_logs=False,
        in_cluster=True,                # ← True when running inside K8s cluster
        service_account_name="airflow-scheduler",
    )

    # ── Task 2: Transform ────────────────────────────────────────────────────
    transform = KubernetesPodOperator(
        task_id="transform",
        # TODO: Use a pandas-capable image (e.g., "python:3.12-slim" + pip install pandas)
        # Or build a custom image with pandas pre-installed
        image=None,
        name="k8s-pipeline-transform",
        namespace="airflow",
        # TODO: Write command to:
        #   1. Read /shared/raw.json
        #   2. Use pandas to normalize the JSON into rows
        #   3. Calculate average price per category
        #   4. Write results to /shared/transformed.json
        cmds=None,
        arguments=None,
        volume_mounts=None,
        volumes=None,
        container_resources=None,
        is_delete_operator_pod=False,
        get_logs=False,
        in_cluster=True,
        service_account_name="airflow-scheduler",
    )

    # ── Task 3: Load ─────────────────────────────────────────────────────────
    load = KubernetesPodOperator(
        task_id="load",
        # TODO: Use "python:3.12-slim" and pip install psycopg2-binary
        # Command should read /shared/transformed.json and INSERT into Postgres
        image=None,
        name="k8s-pipeline-load",
        namespace="airflow",
        cmds=None,
        arguments=None,
        # TODO: Add env_vars for DB connection:
        # PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
        # Use k8s.V1EnvVar with valueFrom.secretKeyRef to read from a K8s Secret
        env_vars=None,
        volume_mounts=None,
        volumes=None,
        container_resources=None,
        is_delete_operator_pod=False,
        get_logs=False,
        in_cluster=True,
        service_account_name="airflow-scheduler",
    )

    # TODO: Wire up task dependencies
    # extract >> transform >> load
