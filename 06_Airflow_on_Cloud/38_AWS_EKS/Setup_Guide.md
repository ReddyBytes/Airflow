# 🔧 EKS Setup Guide — Airflow 3 Step-by-Step

> Deploy Airflow 3 on Amazon EKS using the official Helm chart with KubernetesExecutor.

**Prerequisites:**
- AWS CLI configured (`aws configure`)
- `eksctl` installed ([install guide](https://eksctl.io/installation/))
- `kubectl` installed
- `helm` v3 installed
- AWS account with permissions to create EKS, RDS, IAM resources

**Total time:** ~45–60 minutes

---

## Step 1 — Create the EKS Cluster

```bash
# Create a cluster with a managed node group
# Takes 10–15 minutes
eksctl create cluster \
  --name airflow-cluster \
  --region us-east-1 \
  --nodegroup-name airflow-nodes \
  --node-type m5.large \
  --nodes-min 2 \
  --nodes-max 8 \
  --managed

# Verify nodes are Ready
kubectl get nodes
# Expected: 2 nodes with STATUS=Ready

# Create a dedicated namespace for Airflow
kubectl create namespace airflow
```

---

## Step 2 — Set Up RDS PostgreSQL (Metadata DB)

```bash
# Get your VPC ID and subnet IDs from the EKS cluster
VPC_ID=$(aws eks describe-cluster \
  --name airflow-cluster \
  --query 'cluster.resourcesVpcConfig.vpcId' \
  --output text)

# Create a DB subnet group (use your private subnets)
aws rds create-db-subnet-group \
  --db-subnet-group-name airflow-db-subnet \
  --db-subnet-group-description "Airflow metadata DB" \
  --subnet-ids subnet-abc123 subnet-def456

# Create the RDS instance
aws rds create-db-instance \
  --db-instance-identifier airflow-metadata-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.4 \
  --master-username airflow \
  --master-user-password "YourStrongPassword123!" \
  --db-name airflow \
  --db-subnet-group-name airflow-db-subnet \
  --vpc-security-group-ids sg-yoursgid \
  --allocated-storage 20 \
  --no-publicly-accessible \
  --backup-retention-period 7

# Wait for RDS to be available (5–10 minutes)
aws rds wait db-instance-available \
  --db-instance-identifier airflow-metadata-db

# Get the RDS endpoint (you'll need this in values.yaml)
aws rds describe-db-instances \
  --db-instance-identifier airflow-metadata-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```

---

## Step 3 — Add the Airflow Helm Repository

```bash
# Add the official Apache Airflow Helm chart repo
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# Check available Airflow 3 chart versions
helm search repo apache-airflow/airflow --versions | head -5
```

---

## Step 4 — Create values.yaml

Create a `values.yaml` file with your configuration. This is the heart of your EKS deployment:

```yaml
# values.yaml — Airflow 3 on EKS with KubernetesExecutor

# ── Airflow version ──────────────────────────────────────
airflowVersion: "3.0.0"

# ── Executor ─────────────────────────────────────────────
# KubernetesExecutor: each task runs in its own isolated pod
executor: "KubernetesExecutor"

# ── Metadata Database (RDS PostgreSQL) ───────────────────
data:
  metadataConnection:
    user: airflow
    pass: "YourStrongPassword123!"
    protocol: postgresql
    host: airflow-metadata-db.abc123.us-east-1.rds.amazonaws.com
    port: 5432
    db: airflow

# ── DAG deployment via GitSync ───────────────────────────
dags:
  gitSync:
    enabled: true
    repo: https://github.com/your-org/airflow-dags.git
    branch: main
    depth: 1
    wait: 60          # re-sync every 60 seconds
    subPath: "dags/"
    # For private repos, create a secret:
    #   kubectl create secret generic git-credentials \
    #     --from-literal=GIT_SYNC_USERNAME=your-user \
    #     --from-literal=GIT_SYNC_PASSWORD=your-pat \
    #     -n airflow
    # credentialsSecret: git-credentials

# ── Remote logging to S3 ─────────────────────────────────
logs:
  persistence:
    enabled: false  # disable local PVC; use S3 instead

config:
  logging:
    remote_logging: "True"
    remote_log_conn_id: "aws_default"
    remote_base_log_folder: "s3://your-airflow-logs-bucket/logs"

# ── Webserver ────────────────────────────────────────────
webserver:
  replicas: 2
  service:
    type: ClusterIP  # use ClusterIP + Ingress for production HTTPS
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: "1"
      memory: 2Gi

# ── Scheduler ────────────────────────────────────────────
scheduler:
  replicas: 1       # Airflow 3 supports HA scheduler (standby mode)
  resources:
    requests:
      cpu: "1"
      memory: 2Gi
    limits:
      cpu: "2"
      memory: 4Gi

# ── Triggerer (for deferrable operators) ─────────────────
triggerer:
  enabled: true
  replicas: 1
  resources:
    requests:
      cpu: 250m
      memory: 512Mi
    limits:
      cpu: 500m
      memory: 1Gi

# ── Default task pod resources ───────────────────────────
workers:
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: "2"
      memory: 4Gi

# ── Service account with IRSA ────────────────────────────
serviceAccount:
  create: true
  name: airflow-worker
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789012:role/airflow-worker-role"

# ── Extra environment variables ──────────────────────────
env:
  - name: AIRFLOW__CORE__DEFAULT_TIMEZONE
    value: "UTC"
  - name: AIRFLOW__WEBSERVER__EXPOSE_CONFIG
    value: "False"
  - name: AIRFLOW__CORE__LOAD_EXAMPLES
    value: "False"
  - name: AIRFLOW__CORE__DEFAULT_POOL_TASK_SLOT_COUNT
    value: "128"

# ── Extra pip packages ───────────────────────────────────
extraPipPackages:
  - "apache-airflow-providers-amazon==8.0.0"
  - "apache-airflow-providers-postgres==5.5.0"
  - "pandas==2.0.0"
```

---

## Step 5 — Set Up IRSA (IAM Role for Worker Pods)

```bash
# Associate OIDC provider with your cluster (one-time setup)
eksctl utils associate-iam-oidc-provider \
  --cluster airflow-cluster \
  --region us-east-1 \
  --approve

# Create an IAM policy for Airflow workers
cat > airflow-worker-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Logs",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::your-airflow-logs-bucket",
        "arn:aws:s3:::your-airflow-logs-bucket/*"
      ]
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:airflow/*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name AirflowWorkerPolicy \
  --policy-document file://airflow-worker-policy.json

# Create the IAM service account (links IAM role ↔ K8s service account)
eksctl create iamserviceaccount \
  --cluster airflow-cluster \
  --region us-east-1 \
  --namespace airflow \
  --name airflow-worker \
  --attach-policy-arn arn:aws:iam::123456789012:policy/AirflowWorkerPolicy \
  --override-existing-serviceaccounts \
  --approve
```

---

## Step 6 — Deploy Airflow with Helm

```bash
# Install Airflow (takes 3–5 minutes)
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml \
  --timeout 10m \
  --wait

# Check pod status
kubectl get pods -n airflow

# Expected output:
# NAME                                 READY   STATUS    RESTARTS   AGE
# airflow-scheduler-6d9b9f7b-xxx       2/2     Running   0          2m
# airflow-webserver-8b4f5c9d-xxx       1/1     Running   0          2m
# airflow-triggerer-7c8d6e5f-xxx       1/1     Running   0          2m
# airflow-statsd-9f8e7d6c-xxx          1/1     Running   0          2m
```

**After changing values.yaml, upgrade with:**
```bash
helm upgrade airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml \
  --timeout 10m
```

---

## Step 7 — Access the Airflow UI

```bash
# Option A: Port-forward for local access (development)
kubectl port-forward svc/airflow-webserver 8080:8080 -n airflow &
# Open: http://localhost:8080
# Default credentials: admin / admin

# Option B: Get LoadBalancer URL (if you set service type: LoadBalancer)
kubectl get svc airflow-webserver -n airflow
# Look for EXTERNAL-IP column

# Change the default admin password immediately
kubectl exec -it deploy/airflow-webserver -n airflow -- \
  airflow users reset-password \
  --username admin \
  --use-random-password
```

---

## Step 8 — Deploy Your First DAG

```bash
# If using gitSync: push the DAG to your repo
# Airflow picks it up within 60 seconds

# Or test with a simple DAG directly in the scheduler pod
kubectl exec -it deploy/airflow-scheduler -n airflow -- bash

# Inside the pod:
cat > /opt/airflow/dags/hello_world.py << 'EOF'
from airflow.sdk import DAG, task
from datetime import datetime

with DAG(
    dag_id="hello_world",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    @task
    def say_hello():
        print("Hello from EKS!")
        return "success"

    say_hello()
EOF

# Trigger a test run
airflow dags trigger hello_world

# Watch the task pod appear
exit
kubectl get pods -n airflow -w
# You should see a new pod appear, run, then complete
```

---

## Step 9 — Verify and Troubleshoot

```bash
# All pods running?
kubectl get pods -n airflow

# Check scheduler logs
kubectl logs deploy/airflow-scheduler -n airflow -c scheduler --tail=50

# Check for DAG parsing errors
kubectl logs deploy/airflow-scheduler -n airflow -c scheduler | grep ERROR

# List all DAGs the scheduler knows about
kubectl exec -it deploy/airflow-scheduler -n airflow -- airflow dags list

# Test a specific DAG (dry run)
kubectl exec -it deploy/airflow-scheduler -n airflow -- \
  airflow dags test hello_world 2024-01-01

# View task pod logs after it runs
# Pod name format: airflow-{dag_id}-{task_id}-{date}-{attempt}
kubectl logs airflow-hello-world-say-hello-20240101-1 -n airflow

# Clean up completed task pods
kubectl delete pods -n airflow --field-selector=status.phase=Succeeded
```

---

## Common Issues

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Scheduler pod in CrashLoopBackOff | Wrong RDS endpoint or password | Check `data.metadataConnection` in values.yaml |
| DAGs not appearing | GitSync misconfigured | Check gitSync logs: `kubectl logs -n airflow -l component=scheduler -c git-sync` |
| Task pods not starting | IRSA role missing | Verify service account annotation matches IAM role ARN |
| OOMKilled on task pods | Memory limit too low | Increase `workers.resources.limits.memory` |
| "Connection refused" on webserver | Webserver not ready | Wait 2–3 more minutes; check webserver pod logs |

---

## Next Steps

- [MWAA →](../39_MWAA/Theory.md) — Compare with the managed option
- [GCP Composer →](../40_GCP_Composer/Theory.md) — Google's managed Airflow
- [Cloud Overview →](../37_Cloud_Overview/Theory.md) — Full decision framework
