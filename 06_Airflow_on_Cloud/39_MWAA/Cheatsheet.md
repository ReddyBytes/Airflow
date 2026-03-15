# Amazon MWAA — Cheatsheet

Amazon Managed Workflows for Apache Airflow (MWAA) is AWS's fully managed Airflow
service. You upload your DAGs to S3, configure an environment, and AWS handles
everything else — workers, scheduler, webserver, upgrades, and patches.

---

## What MWAA Manages For You

- Apache Airflow installation and version upgrades
- Scheduler high-availability (2 schedulers by default since Airflow 2.x)
- Worker auto-scaling (CeleryExecutor)
- Webserver behind an ALB
- Metadata DB (managed Aurora Postgres)
- Log shipping to CloudWatch

---

## Core Concepts

| Concept | Description |
|---|---|
| **Environment** | The top-level MWAA resource; maps 1-to-1 with an Airflow installation |
| **S3 Bucket** | Stores `dags/`, `requirements.txt`, and `plugins.zip` |
| **Execution Role** | IAM role assumed by Airflow workers; needs S3, CloudWatch, Secrets Manager perms |
| **Environment Class** | Controls vCPU/RAM per worker: `mw1.small`, `mw1.medium`, `mw1.large`, `mw1.xlarge`, `mw1.2xlarge` |
| **Max Workers** | Upper bound for auto-scaling (default 10, max 25) |
| **Min Workers** | Floor for auto-scaling (default 1) |
| **Schedulers** | Fixed at 2 for HA |

---

## Supported Airflow Versions (as of 2025)

MWAA lags GA Airflow releases by several weeks/months. Always check:
```
https://docs.aws.amazon.com/mwaa/latest/userguide/airflow-versions.html
```

Current supported versions include 2.8.x, 2.9.x, 2.10.x. Airflow 3 support
is expected in 2025/2026.

---

## DAG Deployment

```bash
# Sync DAGs to S3 (MWAA polls S3 every ~30 seconds)
aws s3 sync ./dags s3://my-mwaa-bucket/dags/

# Upload requirements
aws s3 cp requirements.txt s3://my-mwaa-bucket/requirements.txt

# Upload plugins
zip -r plugins.zip plugins/
aws s3 cp plugins.zip s3://my-mwaa-bucket/plugins.zip
```

After uploading `requirements.txt` or `plugins.zip`, you must trigger an environment
update for them to take effect.

---

## AWS CLI Commands

```bash
# Create environment
aws mwaa create-environment \
  --name my-airflow-env \
  --airflow-version 2.10.3 \
  --source-bucket-arn arn:aws:s3:::my-mwaa-bucket \
  --dag-s3-path dags/ \
  --requirements-s3-path requirements.txt \
  --plugins-s3-path plugins.zip \
  --execution-role-arn arn:aws:iam::123456789:role/MWAAExecutionRole \
  --network-configuration SubnetIds=subnet-aaa,subnet-bbb,SecurityGroupIds=sg-xxx \
  --environment-class mw1.medium \
  --min-workers 1 \
  --max-workers 10 \
  --region eu-west-1

# Update environment (e.g. after new requirements.txt)
aws mwaa update-environment \
  --name my-airflow-env \
  --requirements-s3-object-version <s3-version-id>

# Get webserver URL
aws mwaa get-environment --name my-airflow-env \
  --query 'Environment.WebserverUrl' --output text

# Create short-lived web login token (for SSO)
aws mwaa create-web-login-token \
  --name my-airflow-env

# Trigger DAG via MWAA CLI token
MWAA_CLI_TOKEN=$(aws mwaa create-cli-token --name my-airflow-env --query CliToken --output text)
curl -X POST "https://<webserver-host>/aws_mwaa/cli" \
  -H "Authorization: Bearer $MWAA_CLI_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "dags trigger my_dag"
```

---

## IAM Execution Role — Minimum Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:GetObject","s3:GetObjectVersion","s3:ListBucket"],
      "Resource": ["arn:aws:s3:::my-mwaa-bucket","arn:aws:s3:::my-mwaa-bucket/*"] },
    { "Effect": "Allow", "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:log-group:airflow-*" },
    { "Effect": "Allow", "Action": ["cloudwatch:PutMetricData"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["sqs:*"], "Resource": "arn:aws:sqs:*:*:airflow-celery-*" },
    { "Effect": "Allow", "Action": ["kms:GenerateDataKey*","kms:Decrypt"],
      "Resource": "*", "Condition": {"StringLike": {"kms:ViaService": ["sqs.*.amazonaws.com","s3.*.amazonaws.com"]}} }
  ]
}
```

Add further statements for Secrets Manager, RDS, Glue, etc., as your DAGs need them.

---

## Networking Requirements

- MWAA **must** run inside a VPC.
- Requires **2 private subnets** in different AZs (no public subnets for workers).
- The VPC needs either a NAT Gateway or VPC endpoints for: `s3`, `sqs`, `kms`,
  `logs`, `monitoring`, `ecr.api`, `ecr.dkr`.
- Webserver can be `PRIVATE_ONLY` (IAM + VPN) or `PUBLIC_NETWORK` (HTTPS + IAM token).

---

## Environment Class Sizing Guide

| Class | vCPU/worker | RAM/worker | Use case |
|---|---|---|---|
| `mw1.small` | 1 | 2 GB | Dev/test |
| `mw1.medium` | 2 | 4 GB | Small production |
| `mw1.large` | 4 | 8 GB | Standard production |
| `mw1.xlarge` | 8 | 16 GB | Heavy ML/ETL |
| `mw1.2xlarge` | 16 | 32 GB | Very large workloads |

---

## MWAA Limits

| Limit | Value |
|---|---|
| Max workers | 25 |
| Max DAGs | 1000 per environment |
| `requirements.txt` install timeout | 10 minutes |
| `plugins.zip` size | 1 GB |
| Concurrent DAG runs per DAG | 16 (configurable) |
| Airflow UI session timeout | 12 hours |

---

## MWAA vs EKS — Quick Reference

| | MWAA | EKS |
|---|---|---|
| Setup time | ~30 min | Hours–days |
| Executor | CeleryExecutor only | Any |
| Cost predictability | High | Variable |
| Per-task custom images | No | Yes (KPO) |
| Airflow version control | AWS controls | You control |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Previous: EKS** | [38_AWS_EKS](../38_AWS_EKS/Theory.md) |
| **Next: GCP Composer** | [40_GCP_Composer](../40_GCP_Composer/Theory.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
