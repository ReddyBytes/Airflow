# ☁️ Cloud Deployment Comparison

> Detailed feature comparison across the three main Airflow production deployment options.

---

## Full Comparison Table

| Feature | Self-Managed (EKS) | Amazon MWAA | Cloud Composer 2 |
|---------|-------------------|-------------|-----------------|
| **Setup Time** | 2–4 days (k8s + Helm + networking) | 30–60 minutes (console/CLI) | 30–60 minutes (gcloud/console) |
| **Airflow Version** | Any version — you choose | AWS-selected; typically 1–2 minor versions behind open source | Google-selected; typically 1–2 minor versions behind open source |
| **Airflow 3 Support** | Available now (you deploy it) | Dependent on AWS timeline | Dependent on Google timeline |
| **Cost Model** | Pay for EC2/EKS nodes + RDS; no Airflow licensing fee | Hourly per environment size (e.g., mw1.small ~$0.49/hr) | GKE node cost + Composer management fee |
| **Approximate Monthly Cost (small)** | $150–250 | $320–380 | $300–500 |
| **Cost at Scale** | Cheaper (you control instance sizes) | Expensive (fixed tiers) | Moderate |
| **DAG Deployment Method** | GitSync sidecar, S3 via Fuse, direct PVC mount | Upload `.py` files to S3 bucket | Upload `.py` files to GCS bucket |
| **Python Package Management** | Build custom Docker image | `requirements.txt` in S3 (causes env rebuild, 5–20 min) | `requirements.txt` in GCS (causes env rebuild) |
| **Custom Plugins** | Yes — include in Docker image | Yes — `plugins/` folder in S3 | Yes — `plugins/` folder in GCS |
| **Executor** | Any (LocalExecutor, CeleryExecutor, KubernetesExecutor) | CeleryExecutor (fixed) | KubernetesExecutor (fixed) |
| **Scaling** | Manual (configure KEDA or HPA) | Automatic (within tier limits) | Automatic (GKE autoscaling) |
| **Max Concurrent Tasks** | Configurable (limited by cluster size) | Tier-dependent (mw1.small: 5 workers) | Configurable via environment settings |
| **Metadata DB** | You provision (RDS Postgres recommended) | AWS-managed Aurora Postgres | Google-managed Cloud SQL Postgres |
| **Networking** | VPC you control | Must deploy in your VPC | VPC Peering or shared VPC |
| **IAM / Auth** | IRSA (IAM Roles for Service Accounts) | IAM Execution Role, native AWS integration | Workload Identity (no key files needed) |
| **Secrets Management** | Any backend (Vault, AWS SM, GCP SM) | AWS Secrets Manager (native) | GCP Secret Manager (native) |
| **Monitoring** | You set up (CloudWatch, Prometheus, Grafana) | CloudWatch (built-in) | Cloud Monitoring (built-in) |
| **Logging** | You configure (S3, CloudWatch, Elasticsearch) | CloudWatch Logs (automatic) | Cloud Logging (automatic) |
| **Airflow UI Access** | Port-forward, Load Balancer, or Ingress | AWS console link, or direct URL | Direct URL via Google console |
| **SSH / Shell Access** | Yes — exec into any pod | No | No |
| **Custom airflow.cfg** | Full access | Partial (exposed params only) | Partial (exposed params only) |
| **KubernetesExecutor** | Yes | No | Yes (always on) |
| **CeleryExecutor** | Yes | Yes (always on) | No |
| **EdgeExecutor (Airflow 3)** | Yes | Unlikely near-term | Unlikely near-term |
| **Upgrade Process** | You run `helm upgrade`, test, rollback if needed | AWS manages (you choose version in console) | Google manages (you choose version) |
| **Downtime During Upgrade** | Potentially (if not rolling) | Brief (AWS handles) | Brief (Google handles) |
| **SLA / Uptime Guarantee** | Depends on your k8s setup | 99.9% per AWS SLA | 99.9% per Google SLA |
| **Support** | Community + AWS support for EKS | AWS Support (paid tier) | Google Cloud Support (paid tier) |
| **Vendor Lock-in** | Low (Helm chart is portable) | Medium (S3 paths, IAM roles, CloudWatch) | Medium (GCS paths, Workload Identity) |
| **Best For** | Teams that need latest features, full control | AWS-native data stacks, small ops teams | GCP-native data stacks (BigQuery, Dataflow) |

---

## Package Installation Comparison

One of the biggest operational headaches across all three options is adding Python packages.

| Method | Self-Managed | MWAA | Cloud Composer |
|--------|-------------|------|----------------|
| How | Rebuild Docker image | Upload `requirements.txt` to S3 | Upload `requirements.txt` to GCS |
| Time to apply | Minutes (image pull) | 5–20 minutes (env rebuild) | 10–30 minutes (env rebuild) |
| Downtime? | Zero (rolling update) | Environment unavailable during rebuild | Environment unavailable during rebuild |
| Can pin versions? | Yes | Yes | Yes |
| Can install private packages? | Yes (via image build) | Yes (via `--index-url`) | Yes (via Artifact Registry) |

---

## DAG Deployment Comparison

| Method | Self-Managed | MWAA | Cloud Composer |
|--------|-------------|------|----------------|
| Upload method | GitSync, S3 mount, or CI/CD copy to PVC | `aws s3 cp dag.py s3://bucket/dags/` | `gsutil cp dag.py gs://bucket/dags/` |
| Sync speed | Seconds (gitSync polls every 60s by default) | ~30 seconds | ~1 minute |
| DAG versioning | Full git history | No built-in versioning | No built-in versioning |
| Rollback method | `git revert` + push | Re-upload previous file | Re-upload previous file |
| CI/CD friendly? | Yes (push to git branch) | Yes (upload to S3 in pipeline) | Yes (upload to GCS in pipeline) |

---

## When Each Option Breaks Down

| Scenario | Self-Managed | MWAA | Cloud Composer |
|----------|-------------|------|----------------|
| Need Airflow 3 on day 1 | Works | Must wait for AWS | Must wait for Google |
| 1000 concurrent tasks | Works (scale cluster) | Hit tier limits | Works (scale GKE) |
| Team has no k8s experience | Painful | Works well | Works well |
| Budget < $200/month | Possible | No (minimum ~$320) | No (minimum ~$300) |
| Need custom executor | Yes | No | No |
| Need pod-level isolation | Yes (KubernetesExecutor) | No | Yes (KubernetesExecutor) |
| Multi-region active-active | Yes (complex) | No | No |

---

## Summary Recommendation

```
If your team has k8s experience and wants Airflow 3 features → Self-Managed EKS/GKE
If your stack is AWS and you want zero infra work → MWAA
If your stack is GCP (BigQuery, Dataflow) → Cloud Composer 2
```

See [Theory.md](./Theory.md) for the full decision flowchart.
