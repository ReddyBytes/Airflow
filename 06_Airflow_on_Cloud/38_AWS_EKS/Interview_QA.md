# Airflow on AWS EKS — Interview Q&A

These questions come up in data engineering and platform engineering interviews when
the role involves deploying or maintaining Airflow at scale on AWS.

---

## Q1. Why would you choose EKS over MWAA for running Airflow?

**Answer:**
EKS is preferred when you need:

- **KubernetesExecutor** — each task runs in its own pod, giving full isolation, custom
  images per task, and no noisy-neighbour effects between tasks.
- **Full configuration control** — every `airflow.cfg` setting is available via
  `values.yaml` or environment variables.
- **Cost optimisation** — you can use EC2 Spot instances for worker nodes, which can
  cut compute costs by 60–80 % versus On-Demand.
- **Custom provider packages** — no environment-size limits; install anything.
- **Multi-tenancy** — namespace-level isolation per team.

MWAA trades that flexibility for zero operational overhead. It only supports
CeleryExecutor and has stricter limits on plugins and package sizes.

---

## Q2. Walk me through how the Airflow Helm chart deploys components on EKS.

**Answer:**
The official `apache-airflow` Helm chart creates:

| Kubernetes Resource | Airflow Component |
|---|---|
| `Deployment` | Webserver, Scheduler, Triggerer |
| `StatefulSet` | Workers (CeleryExecutor only) |
| `CronJob` | `airflow db migrate` (optional) |
| `ServiceAccount` | IRSA annotation for IAM role |
| `ConfigMap` | `airflow.cfg` overrides |
| `Secret` | Fernet key, webserver secret, DB password |

With `KubernetesExecutor`, there are no persistent worker pods — the scheduler
spawns a pod per task directly via the Kubernetes API.

Key install command:
```bash
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml
```

---

## Q3. What is IRSA and why is it important for Airflow on EKS?

**Answer:**
IRSA (IAM Roles for Service Accounts) lets Kubernetes pods assume an AWS IAM role
without storing long-lived credentials. The mechanism:

1. An OIDC identity provider is registered for the EKS cluster.
2. An IAM role is created with a trust policy scoped to a specific Kubernetes
   ServiceAccount.
3. The ServiceAccount is annotated with the role ARN:
   ```yaml
   annotations:
     eks.amazonaws.com/role-arn: arn:aws:iam::123456789:role/AirflowWorkerRole
   ```
4. AWS injects a short-lived token into every pod using that ServiceAccount.

For Airflow this means tasks can read/write S3, call Secrets Manager, or access
RDS without any hard-coded credentials in DAGs or Docker images.

---

## Q4. How do you deploy DAGs to Airflow on EKS?

**Answer:**
Three common patterns:

1. **GitSync sidecar** — a sidecar container in the scheduler (and workers with
   KubernetesExecutor pod templates) polls a Git repo and syncs the `dags/`
   folder. Zero-downtime, no image rebuild per DAG change. Good default.

2. **Baked into the image** — DAGs are `COPY`-ed into the Docker image. Every DAG
   change requires an image rebuild and a Helm upgrade. Slower iteration but
   perfectly reproducible.

3. **PersistentVolume (EFS/EBS)** — DAGs are placed on a shared volume. Works but
   adds infrastructure complexity; EFS is preferred for multi-pod access.

For CI/CD: most teams use GitSync for development and image-baking for production
to ensure exact reproducibility.

---

## Q5. How does KubernetesExecutor work differently from CeleryExecutor?

**Answer:**

| Aspect | CeleryExecutor | KubernetesExecutor |
|---|---|---|
| Worker type | Long-running pods | Ephemeral pods (one per task) |
| Task isolation | Shared process | Full pod isolation |
| Resource allocation | Fixed worker size | Per-task resource requests |
| Cold start | None (workers pre-warmed) | Pod startup latency (~10–30 s) |
| Custom images | Single image for all tasks | Per-task image override possible |
| Broker required | Yes (Redis/RabbitMQ) | No |

KubernetesExecutor is better for bursty workloads with heterogeneous resource
requirements. CeleryExecutor is better for high-throughput pipelines where cold
start latency matters.

---

## Q6. How do you pass secrets securely to Airflow tasks on EKS?

**Answer:**
Three approaches, from simplest to most secure:

1. **Airflow Variables/Connections** stored in the metadata DB (encrypted with
   Fernet key). Fine for non-critical config.

2. **Kubernetes Secrets** mounted as environment variables or files into task pods:
   ```yaml
   # values.yaml
   secret:
     - envName: DB_PASSWORD
       secretName: my-db-secret
       secretKey: password
   ```

3. **AWS Secrets Manager via IRSA** — tasks call Secrets Manager at runtime using
   the pod's IAM role. No secret ever lives in Kubernetes. Use the
   `SecretsManagerBackend` in Airflow:
   ```ini
   [secrets]
   backend = airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend
   backend_kwargs = {"connections_prefix": "airflow/connections", "variables_prefix": "airflow/variables"}
   ```

---

## Q7. How do you scale Airflow workers on EKS?

**Answer:**

- **KubernetesExecutor**: scaling is automatic — the scheduler creates more pods as
  tasks queue up. Scale the node group using Cluster Autoscaler or Karpenter.
  Configure `[kubernetes] worker_pods_creation_batch_size` for burst control.

- **CeleryExecutor**: add more worker replicas (`workers.replicas` in values.yaml)
  or use KEDA (Kubernetes Event Driven Autoscaler) to scale worker pods based on
  the Celery queue length.

Karpenter is recommended over Cluster Autoscaler on EKS because it provisions
nodes faster and supports Spot interruption handling natively.

---

## Q8. How would you configure RDS Postgres as the metadata DB?

**Answer:**

1. Create an RDS Postgres instance in the same VPC as the EKS cluster.
2. Create a security group rule allowing the EKS node security group to reach
   RDS on port 5432.
3. Store the password in AWS Secrets Manager.
4. Create a Kubernetes secret from the RDS password:
   ```bash
   kubectl create secret generic airflow-db-secret \
     --from-literal=connection=postgresql+psycopg2://airflow:<pass>@<rds-host>:5432/airflow \
     -n airflow
   ```
5. Reference it in `values.yaml`:
   ```yaml
   data:
     metadataSecretName: airflow-db-secret
   ```
6. Disable the built-in Postgres subchart: `postgresql.enabled: false`.

---

## Q9. How do you set up CI/CD for DAG deployment on EKS?

**Answer:**
Common GitHub Actions pipeline:

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
    paths: ['dags/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install apache-airflow && python -m py_compile dags/*.py

  deploy:
    needs: validate
    steps:
      - name: Sync to S3 (if using S3 DAG store)
        run: aws s3 sync dags/ s3://my-dags-bucket/dags/
```

With GitSync, the CI step is just validation — GitSync handles the actual sync.
For image-baking workflows, the CI pipeline builds and pushes a Docker image,
then runs `helm upgrade` to roll out the new image.

---

## Q10. How do you monitor Airflow on EKS?

**Answer:**

- **Prometheus + Grafana**: the Helm chart exposes a `/metrics` endpoint on the
  scheduler and webserver. Use `serviceMonitor.enabled: true` with Prometheus
  Operator.
- **StatsD**: Airflow emits StatsD metrics; forward to Datadog or InfluxDB.
- **CloudWatch Container Insights**: enable on the EKS cluster for node/pod
  CPU and memory.
- **Airflow built-in**: Health check endpoint at `/health`; DAG audit logs in the
  UI.
- **Alerting**: configure `[smtp]` or Slack callbacks in DAGs for task-level
  failure alerts.

---

## Q11. What are the trade-offs of EKS vs MWAA in a production decision?

**Answer:**

| Criterion | EKS | MWAA |
|---|---|---|
| Time to first DAG | Hours–days | ~30 minutes |
| Monthly cost (idle) | ~$150 (2 nodes) | ~$500 (minimum env) |
| Ops team required | Yes | No |
| Airflow version lag | None | Weeks behind GA |
| Compliance | Full control | AWS-managed patching |
| Executor | Any | CeleryExecutor only |

**Rule of thumb**: MWAA for teams that want managed infra and have straightforward
pipelines. EKS when you have a platform team, need KubernetesExecutor, or have
cost/compliance requirements that MWAA cannot meet.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Setup Guide** | [Setup_Guide.md](./Setup_Guide.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
| **Next: MWAA** | [39_MWAA](../39_MWAA/Theory.md) |
