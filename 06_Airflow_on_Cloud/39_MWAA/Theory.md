# ☁️ Amazon MWAA — Managed Airflow on AWS

> *MWAA is the "set it and forget it" option. Upload your DAGs to S3, click create environment, done. No Kubernetes, no Helm, no server management. You spend your time writing DAGs, not maintaining infrastructure. The trade-off: you're paying for that convenience, and you have less control.*

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Architecture](#architecture) · [How DAG Deployment Works](#how-dag-deployment-works) · [Connecting to AWS Services](#connecting-to-aws-services)

**Should Learn** — important for real projects and interviews:
[Installing Python Packages](#installing-python-packages) · [Accessing Connections Securely](#accessing-connections-securely) · [MWAA vs Self-Managed](#mwaa-vs-self-managed-the-honest-trade-off)

**Good to Know** — useful in specific situations, not needed daily:
[VPC Requirements](#vpc-requirements) · [Environment Tiers](#environment-tiers)

**Reference** — skim once, look up when needed:
[Limitations Summary](#limitations-summary) · [Airflow Version Support](#airflow-version-support)

---

## The Story

Your data team needs Airflow in production by end of the week. No one knows Kubernetes. Your DevOps engineer is on holiday. You have three days and a deadline.

You open the AWS console, search for MWAA, click "Create environment," fill in your S3 bucket name and VPC settings, click create — and wait 25 minutes.

When it's done, you have a fully operational, highly available Airflow instance with automatic scaling, managed PostgreSQL, managed Redis, built-in CloudWatch logging, and IAM authentication. You didn't install anything.

You upload your DAG file to S3. Thirty seconds later, it appears in the Airflow UI. You trigger it. It runs.

This is MWAA's value proposition: **you write DAGs, AWS runs Airflow.** For many teams, that trade-off is worth it.

---

## Architecture

```mermaid
flowchart TD
    subgraph Account["Your AWS Account"]
        subgraph VPC["Your VPC — Private Subnets"]
            subgraph MWAA_ENV["MWAA Environment (AWS-managed)"]
                WS[Airflow Webserver\nHTTPS endpoint\nAWS-managed]
                SC[Airflow Scheduler\nHA by default\nAWS-managed]
                WRK[Celery Workers\nAuto-scaled 1–N\nAWS-managed]
                MetaDB[(PostgreSQL\nMetadata DB\nAWS-managed)]
                Redis[(Redis Broker\nCelery\nAWS-managed)]
            end
        end

        subgraph S3["S3 Bucket (your bucket)"]
            DAGS[dags/ folder\n.py DAG files]
            REQS[requirements.txt\nPython packages]
            PLUGINS[plugins/ folder\nCustom operators]
        end

        subgraph Secrets["AWS Secrets Manager"]
            CONN[airflow/connections/*\nConnection credentials]
            VARS[airflow/variables/*\nSecrets and config]
        end

        CW[CloudWatch Logs\nTask + scheduler logs\nautomatic]
    end

    DEV([Developer]) -->|aws s3 cp| DAGS
    MWAA_ENV -->|polls every 30s| S3
    MWAA_ENV -->|reads credentials| Secrets
    MWAA_ENV -->|writes logs| CW

    style MWAA_ENV fill:#FF9900,color:#fff
    style S3 fill:#E8F5E9
    style Secrets fill:#E3F2FD
```

---

## How DAG Deployment Works

This is the biggest operational difference from self-managed Airflow. There is no SSH. There is no `kubectl exec`. You just upload a Python file to S3.

```
Your repo
    └── dags/
        ├── etl_pipeline.py
        ├── data_quality.py
        └── ml_training.py

      ↓ aws s3 sync

S3 bucket: s3://my-airflow-bucket/
    ├── dags/
    │   ├── etl_pipeline.py     ← Airflow picks this up in ~30s
    │   ├── data_quality.py
    │   └── ml_training.py
    ├── requirements.txt        ← Python packages
    └── plugins/                ← Custom operators/hooks
        └── my_custom_hook.py
```

```bash
# Deploy a single DAG
aws s3 cp my_dag.py s3://my-airflow-bucket/dags/my_dag.py

# Deploy all DAGs (sync entire folder)
aws s3 sync ./dags/ s3://my-airflow-bucket/dags/

# Remove a DAG
aws s3 rm s3://my-airflow-bucket/dags/old_dag.py
# Note: removing from S3 doesn't remove it from the Airflow DB
# You must also delete it from the Airflow UI
```

MWAA's scheduler polls your `dags/` prefix every ~30 seconds. New or changed files appear in the UI within 1–2 minutes.

---

## Airflow Version Support

MWAA supports specific Airflow versions certified by AWS. New Airflow versions typically arrive 3–6 months after the open-source release.

| What you want | MWAA? |
|---------------|-------|
| Airflow 2.x (stable) | Yes — well supported |
| Airflow 3.0 on day one | No — wait for AWS certification |
| Latest Airflow 3 features immediately | No — use self-managed EKS |

Check [aws.amazon.com/mwaa](https://aws.amazon.com/managed-workflows-for-apache-airflow/) for current supported versions.

---

## Installing Python Packages

MWAA installs packages from a `requirements.txt` in your S3 bucket. The critical caveat: **updating `requirements.txt` causes the environment to rebuild, which takes 10–25 minutes, during which your environment is unavailable.**

```bash
# Create requirements.txt
cat > requirements.txt << 'EOF'
apache-airflow-providers-snowflake==4.0.0
apache-airflow-providers-databricks==4.1.0
pandas==2.0.0
boto3==1.28.0
EOF

# Upload to S3
aws s3 cp requirements.txt s3://my-airflow-bucket/requirements.txt
```

After uploading, update the environment via the console (or AWS CLI) to point to the new file. The environment rebuilds.

**Important warnings:**
- Do NOT include `apache-airflow` itself in `requirements.txt` — MWAA manages the Airflow version
- Test package compatibility locally before uploading — a version conflict can break the entire environment
- Pin all package versions — floating versions cause non-reproducible builds

---

## Environment Tiers

MWAA has three environment sizes. You cannot switch between them without recreating the environment.

| Class | Workers | vCPU per Worker | RAM per Worker | Best For |
|-------|---------|-----------------|----------------|----------|
| `mw1.micro` | 1–5 | 1 | 2 GB | Development only |
| `mw1.small` | 1–5 | 2 | 4 GB | Small production |
| `mw1.medium` | 1–8 | 4 | 8 GB | Medium production |
| `mw1.large` | 1–10 | 8 | 16 GB | Large production |

---

## VPC Requirements

MWAA must run in a VPC with **private subnets in at least two Availability Zones**. This is non-negotiable.

```mermaid
flowchart LR
    subgraph VPC["Your VPC"]
        subgraph AZ1["Availability Zone 1"]
            Sub1[Private Subnet 1\ne.g. 10.0.1.0/24]
        end
        subgraph AZ2["Availability Zone 2"]
            Sub2[Private Subnet 2\ne.g. 10.0.2.0/24]
        end
        NAT[NAT Gateway\nfor outbound internet\ne.g. pip install]
    end
    Internet[Internet\npypi.org, package repos]
    NAT --> Internet
```

Key networking requirements:
- **Private subnets** — MWAA cannot run in public subnets
- **NAT Gateway** — needed for workers to reach PyPI and other services
- **Security group** — allow HTTPS (443) outbound for package installation
- **VPC endpoints** (optional but recommended) — for S3, Secrets Manager to avoid NAT costs

---

## Connecting to AWS Services

MWAA uses an **IAM Execution Role** for all AWS access. Attach policies to this role for every AWS service your DAGs use.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
      "Resource": [
        "arn:aws:s3:::my-airflow-bucket",
        "arn:aws:s3:::my-airflow-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:airflow/*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "*"
    }
  ]
}
```

Add more statements for services your DAGs access: Redshift, Glue, EMR, RDS, etc.

---

## Accessing Connections Securely

The cleanest way to manage connections in MWAA is via AWS Secrets Manager. No credentials in the Airflow UI. No environment variables.

```bash
# Create a Postgres connection in Secrets Manager
aws secretsmanager create-secret \
  --name "airflow/connections/my_postgres" \
  --secret-string "postgresql://user:password@host:5432/mydb"

# Create a variable
aws secretsmanager create-secret \
  --name "airflow/variables/s3_bucket" \
  --secret-string "my-data-bucket"
```

In your DAG, use the connection as normal — Airflow resolves it from Secrets Manager automatically:
```python
hook = PostgresHook(postgres_conn_id="my_postgres")
```

Enable this by setting in the MWAA environment configuration:
```
AIRFLOW__SECRETS__BACKEND = airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend
```

---

## MWAA vs Self-Managed: The Honest Trade-off

```mermaid
flowchart LR
    subgraph MWAA["MWAA ☁️"]
        M1[Setup: 30 min]
        M2[Airflow version: AWS picks]
        M3[Executor: CeleryExecutor only]
        M4[Cost: ~$320/mo minimum]
        M5[Debugging: CloudWatch only]
        M6[Packages: 10-25 min to add]
    end

    subgraph EKS["Self-Managed EKS 🔧"]
        E1[Setup: 2-4 days]
        E2[Airflow version: you pick]
        E3[Executor: any]
        E4[Cost: ~$150/mo minimum]
        E5[Debugging: kubectl exec into pods]
        E6[Packages: rebuild image, rolling update]
    end
```

---

## Limitations Summary

| Limitation | Practical Impact |
|-----------|-----------------|
| CeleryExecutor only | Cannot run task-per-pod isolation (KubernetesExecutor) |
| Airflow version lag (3–6 months) | Cannot use Airflow 3 features on day one |
| No SSH to workers | Cannot attach a debugger or inspect the OS |
| Package updates take 10–25 min | Slow iteration during development |
| Minimum ~$320/month | Cannot scale to zero; dev environments are expensive |
| No direct `airflow.cfg` access | Limited to environment variables exposed in the console |
| S3 polling latency | New DAGs take 1–2 minutes to appear |

---

## See Also

- [Cloud Overview →](../37_Cloud_Overview/Theory.md) — Decision framework for choosing MWAA vs EKS vs Composer
- [Comparison Table →](../37_Cloud_Overview/Comparison.md) — Detailed feature comparison
- [GCP Composer →](../40_GCP_Composer/Theory.md) — Google's equivalent managed Airflow
