# Cloud Overview — Cheatsheet

Quick reference for choosing and comparing Airflow deployment options.

---

## The Three Deployment Paths

| Option | Who manages infra | Airflow version | Best for |
|---|---|---|---|
| **Self-managed (EKS/GKE)** | You | Latest | Teams with k8s expertise |
| **Amazon MWAA** | AWS | 1–2 versions behind | AWS-heavy stacks, no k8s team |
| **Cloud Composer** | Google | Slightly behind | GCP-heavy stacks |

---

## Self-Managed vs Managed — Quick Contrast

| Factor | Self-Managed | Managed (MWAA/Composer) |
|---|---|---|
| Setup effort | High | Low |
| Configuration access | Full `airflow.cfg` | Partial |
| Executor choice | Any | MWAA: Celery only · Composer: K8s only |
| Upgrade control | You decide when | Cloud provider controls |
| Cost (small env) | ~$150–250/mo | ~$320–500/mo |
| Debugging infra | You investigate | Cloud support |
| Scaling | Manual (KEDA/HPA) | Automatic |

---

## When to Choose Each

**Self-managed EKS/GKE:**
- Need KubernetesExecutor or custom executors
- Need latest Airflow version (especially Airflow 3)
- Have a DevOps/platform team who owns Kubernetes
- Cost optimisation matters (Spot instances)

**Amazon MWAA:**
- Data stack is primarily AWS (S3, Redshift, Glue, EMR)
- No Kubernetes team available
- AWS-native IAM + CloudWatch is a priority
- Can accept Airflow being 1–2 versions behind

**Cloud Composer:**
- Data stack is primarily GCP (BigQuery, GCS, Dataflow)
- Want Workload Identity — no service account keys
- Already using GKE for other workloads
- Need pre-installed GCP operators

---

## Approximate Monthly Cost

| Deployment | Cost | Notes |
|---|---|---|
| Self-managed EKS (2 nodes) | ~$150–250 | EKS control plane + EC2 + RDS |
| Amazon MWAA (mw1.small) | ~$320–380 | All-in managed price |
| Cloud Composer 2 (small) | ~$300–500 | GKE-based, all components |

---

## Migration Complexity

```
Local docker-compose
    → Self-managed EKS    (add Helm chart + k8s cluster)
    → MWAA                (DAG code reuse + VPC + S3 setup)
    → Cloud Composer      (DAG code reuse + GCS setup)
```

**Rule:** DAG code is portable. Infrastructure and connections are not.

---

## Operational Tasks by Deployment

| Task | Self-managed | MWAA | Composer |
|---|---|---|---|
| Airflow upgrade | Manual, you test | AWS handles | Google handles |
| Python packages | Rebuild image | `requirements.txt` in S3 | `requirements.txt` in GCS |
| Worker scaling | KEDA / HPA | Automatic | Automatic |
| Debugging infra failures | You diagnose k8s | AWS Support | Google Support |
| Custom plugins | Any size | Limited by env size | Limited |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Next: AWS EKS** | [38_AWS_EKS/Theory.md](../38_AWS_EKS/Theory.md) |
| **Next: MWAA** | [39_MWAA/Theory.md](../39_MWAA/Theory.md) |
| **Next: GCP Composer** | [40_GCP_Composer/Theory.md](../40_GCP_Composer/Theory.md) |
