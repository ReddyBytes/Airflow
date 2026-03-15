# Airflow on AWS EKS — Cheatsheet

Running Airflow on Amazon Elastic Kubernetes Service gives you full control over every
component while leaning on managed Kubernetes for the hard parts of cluster lifecycle.
Think of it as "bring your own cluster, let AWS handle the nodes."

---

## Why EKS for Airflow?

| Need | EKS Delivers |
|---|---|
| Full config control | Edit any Airflow setting via `values.yaml` |
| KubernetesExecutor | Each task = isolated pod; no shared state |
| Cost optimisation | Spot instances for workers |
| Custom images | Any Python version, any provider |
| Private networking | VPC-native pods |

---

## Cluster Bootstrap (one-time)

```bash
# 1. Create cluster (eksctl)
eksctl create cluster \
  --name airflow-cluster \
  --region eu-west-1 \
  --nodegroup-name standard-workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 6 \
  --managed

# 2. Add the official Airflow Helm repo
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# 3. Create namespace
kubectl create namespace airflow
```

---

## Helm Install / Upgrade

```bash
# Install
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml \
  --version 1.14.0

# Upgrade after values.yaml changes
helm upgrade airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml

# Check rollout
kubectl rollout status deployment/airflow-webserver -n airflow
```

---

## Key `values.yaml` Settings

```yaml
# Executor
executor: KubernetesExecutor

# Airflow image (pin the tag!)
images:
  airflow:
    repository: apache/airflow
    tag: 2.10.0-python3.11

# Webserver secret key — generate once, store in Secrets Manager
webserverSecretKeySecretName: airflow-webserver-secret

# Metadata DB — point to RDS
data:
  metadataConnection:
    user: airflow
    pass: ~           # use secretName instead in production
    protocol: postgresql
    host: airflow-rds.xxxxxxx.eu-west-1.rds.amazonaws.com
    port: 5432
    db: airflow
    sslmode: require

# DAG deployment — GitSync sidecar
dags:
  gitSync:
    enabled: true
    repo: https://github.com/your-org/airflow-dags.git
    branch: main
    depth: 1
    subPath: dags/
    credentialsSecret: git-credentials

# Log storage — S3
logs:
  persistence:
    enabled: false        # disable PVC
  s3:
    enabled: true
    bucketName: my-airflow-logs
    region: eu-west-1

# Workers (KubernetesExecutor uses pod templates instead)
workers:
  replicas: 0

# Triggerer
triggerer:
  enabled: true
  replicas: 1
```

---

## IAM Service Accounts (IRSA)

IRSA lets pods assume an IAM role without storing credentials.

```bash
# 1. Enable OIDC provider for the cluster
eksctl utils associate-iam-oidc-provider \
  --cluster airflow-cluster --approve

# 2. Create IAM policy (S3 + Secrets Manager access)
aws iam create-policy \
  --policy-name AirflowWorkerPolicy \
  --policy-document file://airflow-iam-policy.json

# 3. Create service account with role annotation
eksctl create iamserviceaccount \
  --name airflow-worker \
  --namespace airflow \
  --cluster airflow-cluster \
  --attach-policy-arn arn:aws:iam::123456789:policy/AirflowWorkerPolicy \
  --approve

# 4. Reference in values.yaml
serviceAccount:
  create: false
  name: airflow-worker
```

---

## S3 for Remote Logs

```yaml
# values.yaml
env:
  - name: AIRFLOW__LOGGING__REMOTE_LOGGING
    value: "True"
  - name: AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER
    value: "s3://my-airflow-logs/logs"
  - name: AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID
    value: "aws_default"
```

With IRSA the pod uses its attached role — no `aws_access_key_id` needed.

---

## RDS Postgres (Metadata DB)

```bash
# Create RDS (Postgres 16 recommended)
aws rds create-db-instance \
  --db-instance-identifier airflow-metadata \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16.2 \
  --master-username airflow \
  --master-user-password <from-secrets-manager> \
  --allocated-storage 20 \
  --vpc-security-group-ids sg-xxxxxxxx \
  --db-subnet-group-name airflow-subnet-group \
  --no-publicly-accessible
```

Store the password in AWS Secrets Manager and reference it via an `ExternalSecret`
or a Kubernetes secret created by your CI/CD pipeline — never hardcode it.

---

## EKS vs MWAA — Decision Table

| Factor | EKS (self-managed) | MWAA (managed) |
|---|---|---|
| Setup effort | High | Low |
| Config flexibility | Full | Limited |
| Cost (small team) | Higher (ops overhead) | Predictable |
| Executor options | Any | CeleryExecutor only |
| Upgrade control | You choose when | AWS controls cadence |
| Custom plugins | Any | Limited by env size |
| Networking | VPC, full control | VPC required, less flexible |

**Choose EKS when** you need KubernetesExecutor, custom images, or cost control via Spot.
**Choose MWAA when** you want zero-ops and Celery is sufficient.

---

## Quick Debugging Commands

```bash
# List all Airflow pods
kubectl get pods -n airflow

# Follow webserver logs
kubectl logs -n airflow deploy/airflow-webserver -f

# Describe a stuck task pod
kubectl describe pod <task-pod-name> -n airflow

# Port-forward webserver locally
kubectl port-forward svc/airflow-webserver 8080:8080 -n airflow

# Shell into scheduler
kubectl exec -it deploy/airflow-scheduler -n airflow -- bash
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Setup Guide** | [Setup_Guide.md](./Setup_Guide.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
| **Next: MWAA** | [39_MWAA](../39_MWAA/Theory.md) |
