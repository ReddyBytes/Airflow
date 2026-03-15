# GCP Cloud Composer — Cheatsheet

Cloud Composer is Google Cloud's fully managed Apache Airflow service, built on
Google Kubernetes Engine. Composer 2 (current generation) introduced auto-scaling
and a fundamentally different architecture where each component scales independently.

---

## What Cloud Composer Manages

- GKE cluster provisioning and upgrades
- Airflow installation and minor-version patches
- Cloud SQL Postgres (metadata DB)
- Cloud Storage bucket for DAGs, logs, plugins, data
- IAM integration via Workload Identity
- Private IP networking
- Airflow UI behind Identity-Aware Proxy (IAP)

---

## Core Concepts

| Concept | Description |
|---|---|
| **Environment** | Top-level resource; one Airflow installation per environment |
| **GCS Bucket** | Auto-created; `dags/` subfolder is the DAG store |
| **Workload Identity** | Maps a Kubernetes ServiceAccount to a GCP service account — no key files |
| **PyPI Packages** | Installed via environment config; no restart for package changes in Composer 2 |
| **Environment Variables** | Set at environment level; available to all Airflow components |
| **Composer 1 vs 2** | Composer 1 = fixed cluster; Composer 2 = autoscaling, pay-per-use |

---

## Environment Tiers (Composer 2)

| Tier | Description |
|---|---|
| `composer-n1-webserver-2` | Development, low traffic |
| `composer-n2-webserver-4` | Small production |
| `composer-n4-webserver-8` | Standard production |
| Custom | Specify `--scheduler-cpu`, `--worker-cpu`, etc. per component |

---

## gcloud Commands

```bash
# Create a Composer 2 environment
gcloud composer environments create my-composer-env \
  --location europe-west2 \
  --image-version composer-2.9.7-airflow-2.9.3 \
  --environment-size small \
  --service-account airflow-sa@my-project.iam.gserviceaccount.com

# List environments
gcloud composer environments list --locations europe-west2

# Describe environment (get DAG bucket, webserver URL, etc.)
gcloud composer environments describe my-composer-env \
  --location europe-west2

# Deploy DAGs
gcloud composer environments storage dags import \
  --environment my-composer-env \
  --location europe-west2 \
  --source ./dags/

# Or sync directly via gsutil
gsutil -m rsync -r ./dags gs://$(gcloud composer environments describe my-composer-env \
  --location europe-west2 --format="value(config.dagGcsPrefix)")

# Install PyPI packages
gcloud composer environments update my-composer-env \
  --location europe-west2 \
  --update-pypi-packages-from-file requirements.txt

# Set environment variable
gcloud composer environments update my-composer-env \
  --location europe-west2 \
  --update-env-variables ENVIRONMENT=production

# Set Airflow config override
gcloud composer environments update my-composer-env \
  --location europe-west2 \
  --update-airflow-configs "core-max_active_tasks_per_dag=32"

# Trigger a DAG
gcloud composer environments run my-composer-env \
  --location europe-west2 \
  dags trigger -- my_dag_id

# List DAG runs
gcloud composer environments run my-composer-env \
  --location europe-west2 \
  dags list-runs -- --dag-id my_dag_id
```

---

## DAG Deployment

```bash
# Method 1: gcloud (single file)
gcloud composer environments storage dags import \
  --environment my-composer-env \
  --location europe-west2 \
  --source my_dag.py

# Method 2: gsutil rsync (CI/CD preferred)
gsutil -m rsync -r -d ./dags/ gs://my-composer-bucket/dags/

# Method 3: GCS FUSE (not recommended for production)
# The DAG folder is mounted as a filesystem inside the scheduler pod.
```

After upload the Airflow scheduler re-scans the DAGs folder within seconds.

---

## Workload Identity Setup

```bash
# 1. Create a GCP service account
gcloud iam service-accounts create airflow-worker-sa \
  --project my-project

# 2. Grant it BigQuery access
gcloud projects add-iam-policy-binding my-project \
  --member "serviceAccount:airflow-worker-sa@my-project.iam.gserviceaccount.com" \
  --role "roles/bigquery.dataEditor"

# 3. Bind it to the Kubernetes ServiceAccount used by Airflow workers
gcloud iam service-accounts add-iam-policy-binding \
  airflow-worker-sa@my-project.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:my-project.svc.id.goog[composer-2/airflow-worker]"
```

With Workload Identity, DAG code can call BigQuery, GCS, Pub/Sub, etc. without
any key files or environment variables containing credentials.

---

## Composer 2 Autoscaling

Composer 2 autoscales at the **task level** using KubernetesExecutor under the hood:

```bash
# Set autoscaling range
gcloud composer environments update my-composer-env \
  --location europe-west2 \
  --min-workers 1 \
  --max-workers 12
```

Each Airflow task runs as an ephemeral Kubernetes pod. Node pool autoscaling is
handled by GKE Autopilot (or a standard node pool with Cluster Autoscaler).

---

## Composer vs Self-Managed GKE — Decision Table

| Factor | Cloud Composer 2 | GKE Self-Managed |
|---|---|---|
| Setup time | ~20 minutes | Hours |
| Ops overhead | Low | High |
| GKE version control | Google manages | You control |
| Custom Airflow config | Partial (UI/gcloud) | Full (values.yaml) |
| Cost | Pay-per-use (Composer 2) | Node cost only |
| Custom executors | No | Yes |
| Workload Identity | Built-in | Manual IRSA-equivalent |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Previous: MWAA** | [39_MWAA](../39_MWAA/Theory.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
| **Next: Integrations** | [07_Integrations](../../07_Integrations/Readme.md) |
