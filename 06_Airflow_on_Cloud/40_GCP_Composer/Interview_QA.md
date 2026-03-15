# GCP Cloud Composer — Interview Q&A

These questions are common in GCP-focused data engineering interviews and platform
engineering roles where Composer is the chosen orchestration platform.

---

## Q1. What is Cloud Composer and how does it differ from raw Airflow on GKE?

**Answer:**
Cloud Composer is a fully managed Airflow service on Google Cloud. Under the hood
it runs on Google Kubernetes Engine, but Google manages:

- The GKE cluster and its lifecycle (upgrades, node pools)
- Airflow installation and configuration scaffolding
- Cloud SQL Postgres for the metadata database
- A GCS bucket auto-created per environment (DAGs, logs, plugins)
- IAP (Identity-Aware Proxy) for webserver authentication
- Workload Identity for GCP service access from DAGs

Running Airflow yourself on GKE gives you full control (any executor, any config,
any Airflow version) but requires a platform team to maintain it. Composer is
the zero-ops path for GCP-native organisations.

---

## Q2. How does Cloud Composer use GKE under the hood?

**Answer:**
Every Composer environment is backed by a dedicated GKE cluster (or a namespace
in a shared cluster for Composer 2 with Private IP). The Airflow components —
scheduler, webserver, triggerer, and workers — run as Kubernetes Deployments or
as ephemeral pods (Composer 2 uses KubernetesExecutor for worker tasks).

In **Composer 2**, Google switched from CeleryExecutor to KubernetesExecutor. Each
Airflow task spawns a pod. GKE Autopilot (or a managed node pool) scales nodes
automatically. This gives better resource utilisation and task isolation compared
to Composer 1's fixed Celery workers.

You never interact with the GKE cluster directly in a managed Composer setup —
all configuration goes through `gcloud composer environments update` or the Cloud
Console.

---

## Q3. How do you deploy DAGs to Cloud Composer?

**Answer:**
Each Composer environment has an associated GCS bucket. The `dags/` prefix within
that bucket is the DAG store. The Airflow scheduler reads from this GCS path:

```bash
# Get the DAG bucket path
DAG_BUCKET=$(gcloud composer environments describe my-env \
  --location europe-west2 \
  --format="value(config.dagGcsPrefix)")

# Sync all DAGs
gsutil -m rsync -r -d ./dags/ $DAG_BUCKET/

# Or use the gcloud wrapper
gcloud composer environments storage dags import \
  --environment my-env \
  --location europe-west2 \
  --source ./dags/my_dag.py
```

The scheduler detects changes within a few seconds. No restart is required.

For CI/CD: a Cloud Build trigger (or GitHub Actions with Workload Identity
Federation) runs `gsutil rsync` on merge to main.

---

## Q4. What is Workload Identity and why is it important for Composer?

**Answer:**
Workload Identity is GKE's mechanism for letting pods assume a GCP IAM service
account without key files. It maps:

```
Kubernetes ServiceAccount (in GKE namespace)
    ↕ IAM binding
GCP Service Account (IAM)
    ↕ IAM role
GCP Resource (BigQuery, GCS, Pub/Sub, …)
```

For Composer, Airflow worker pods run as the Kubernetes ServiceAccount
`airflow-worker` in the Composer namespace. You bind a GCP service account to
this K8s ServiceAccount via:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  my-sa@my-project.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:my-project.svc.id.goog[composer-2/airflow-worker]"
```

DAG code using `google-cloud-bigquery`, `google-cloud-storage`, or any GCP
library will automatically use these credentials — no `GOOGLE_APPLICATION_CREDENTIALS`
environment variable needed.

---

## Q5. How does Composer 2 autoscaling work?

**Answer:**
Composer 2 runs tasks as Kubernetes pods via KubernetesExecutor. Autoscaling
happens at two levels:

1. **Task-level**: the scheduler creates a pod per task. When tasks finish, pods
   are deleted. This is inherent to KubernetesExecutor.

2. **Node-level**: the GKE node pool (or GKE Autopilot) scales the number of nodes
   based on pending pod requests. With Autopilot, Google manages node provisioning
   automatically.

You configure the bounds:
```bash
gcloud composer environments update my-env \
  --location europe-west2 \
  --min-workers 1 \
  --max-workers 10
```

Scale-out latency in Composer 2 is lower than Composer 1 because pod startup is
faster than EC2 launch (Autopilot pre-warms node capacity).

---

## Q6. How do you install Python packages in Cloud Composer?

**Answer:**

```bash
# Option 1: From file
gcloud composer environments update my-env \
  --location europe-west2 \
  --update-pypi-packages-from-file requirements.txt

# Option 2: Individual package
gcloud composer environments update my-env \
  --location europe-west2 \
  --update-pypi-package apache-airflow-providers-snowflake==4.5.0
```

In Composer 2, package installation does not restart the entire environment —
Google applies it in a rolling fashion. Installation still takes 5–15 minutes.

Test package compatibility locally using the Composer version constraints file:
```bash
pip install apache-airflow==2.9.3 \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.11.txt"
```

---

## Q7. How do you handle Airflow configuration overrides in Composer?

**Answer:**
```bash
# Set Airflow config (maps to airflow.cfg sections)
gcloud composer environments update my-env \
  --location europe-west2 \
  --update-airflow-configs \
    "core-max_active_tasks_per_dag=32,scheduler-min_file_process_interval=30"

# Set environment variables (available as process env vars in all pods)
gcloud composer environments update my-env \
  --location europe-west2 \
  --update-env-variables ENVIRONMENT=prod,DATA_LAKE_BUCKET=my-bucket
```

You cannot override every setting — some are managed by Google (e.g., database
connection strings). Attempting to set reserved configs returns an error.

---

## Q8. How do you access GCP secrets from Composer DAGs?

**Answer:**
Two approaches:

1. **Airflow Connections/Variables via Secret Manager backend**:
   ```bash
   gcloud composer environments update my-env \
     --location europe-west2 \
     --update-airflow-configs \
       "secrets-backend=airflow.providers.google.cloud.secrets.secret_manager.CloudSecretManagerSecretsBackend"
   ```
   Airflow resolves connections/variables from Secret Manager paths like
   `airflow-connections-my_conn` automatically.

2. **Direct Secret Manager calls in DAG code** using `google-cloud-secret-manager`:
   ```python
   from google.cloud import secretmanager
   client = secretmanager.SecretManagerServiceClient()
   secret = client.access_secret_version(name="projects/my-project/secrets/my-secret/versions/latest")
   value = secret.payload.data.decode("UTF-8")
   ```
   With Workload Identity, no credentials are needed.

---

## Q9. What are the pricing components of Cloud Composer 2?

**Answer:**

| Component | Pricing Model |
|---|---|
| Composer environment fee | Per environment per hour |
| Scheduler vCPU/RAM | Per vCPU-hour and GB-hour |
| Worker vCPU/RAM | Per vCPU-hour and GB-hour (only when tasks run) |
| Webserver | Per vCPU-hour |
| GKE node pool | Standard GKE pricing (or Autopilot per-pod) |
| Cloud SQL | Standard Cloud SQL pricing |
| GCS storage | Per GB stored for DAGs/logs |

Composer 2 is significantly cheaper than Composer 1 for bursty workloads because
workers only exist while tasks are running.

---

## Q10. Compare Cloud Composer with MWAA.

**Answer:**

| Feature | Cloud Composer 2 | Amazon MWAA |
|---|---|---|
| Cloud provider | GCP | AWS |
| Executor | KubernetesExecutor | CeleryExecutor |
| Autoscaling | Pod + node level | Worker instance level |
| Task isolation | Yes (per-pod) | No (shared workers) |
| Version lag | Weeks | Weeks |
| DAG store | GCS | S3 |
| Credentials | Workload Identity | IAM Execution Role |
| Min monthly cost | ~$300 | ~$350 |
| Custom images | No | No |

**Key difference**: Composer 2 uses KubernetesExecutor giving true task isolation,
while MWAA uses CeleryExecutor with shared workers. For workloads requiring
isolation or heterogeneous resources, Composer 2 is the better managed option.

---

## Q11. When would you choose self-managed Airflow on GKE over Cloud Composer?

**Answer:**
Choose GKE self-managed when:

- You need an executor other than KubernetesExecutor (e.g., LocalExecutor for
  single-node dev, or a custom executor).
- You need Airflow 3 features before Composer supports them.
- You need direct kubectl access to debug worker pods.
- You have strict compliance requirements around what runs on your cluster.
- You need to install system-level packages (`.so` files, CUDA drivers) in the
  Airflow worker image.
- You want to run multiple Airflow versions side-by-side in the same cluster.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Previous: MWAA** | [39_MWAA](../39_MWAA/Theory.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
| **Next: Integrations** | [07_Integrations](../../07_Integrations/Readme.md) |
