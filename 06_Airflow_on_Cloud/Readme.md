<div align="center">
⬅️ [Airflow 3 Features](../05_Airflow_3_Features/Readme.md) &nbsp;|&nbsp; 🏠 [Home](../00_Learning_Guide/Readme.md) &nbsp;|&nbsp; [Integrations ➡️](../07_Integrations/Readme.md)
</div>

---

# ☁️ Airflow on Cloud

> *Running Airflow on your laptop is fine for learning. Running it 24/7 in production, reliably, at scale — that requires cloud infrastructure. Three paths: own everything on Kubernetes, delegate to AWS with MWAA, or delegate to GCP with Cloud Composer.*

**[Start Here → Cloud Overview (Theory.md)](37_Cloud_Overview/Theory.md)**

---

## At a Glance

| | |
|---|---|
| **Topics** | 4 modules |
| **Est. Time** | 10–12 hours |
| **Prerequisites** | 🟣 Expert Track complete, active cloud provider account |
| **Unlocks** | 🔗 Integrations |

---

## Section Map

```mermaid
mindmap
  root((☁️ Cloud))
    Cloud Overview
      Self-managed vs managed
      Cost comparison
      Operational complexity
      Decision framework
    AWS EKS
      eksctl setup
      Helm chart
      values.yaml
      gitSync DAGs
      RDS metadata DB
      IAM roles
      CloudWatch monitoring
    MWAA
      S3 DAG deployment
      requirements.txt
      Environment tiers
      VPC requirements
      Limitations
    GCP Composer
      Composer 2 architecture
      GCS DAG bucket
      Workload Identity
      Pre-installed operators
      Cost model
```

---

## Topics

| Module | File | Description |
|--------|------|-------------|
| 37 | [Cloud Overview → Theory.md](37_Cloud_Overview/Theory.md) | Decision framework: self-managed vs MWAA vs Composer |
| 37 | [Cloud Overview → Comparison](37_Cloud_Overview/Comparison.md) | Detailed feature comparison table |
| 38 | [AWS EKS → Theory.md](38_AWS_EKS/Theory.md) | Full-control Airflow on Kubernetes |
| 38 | [AWS EKS → Setup Guide](38_AWS_EKS/Setup_Guide.md) | Step-by-step EKS deployment commands |
| 39 | [MWAA → Theory.md](39_MWAA/Theory.md) | Managed Airflow on AWS — S3, VPC, tiers |
| 40 | [GCP Composer → Theory.md](40_GCP_Composer/Theory.md) | Managed Airflow on GCP — Composer 2, Workload Identity |

---

## Decision Flowchart

```mermaid
flowchart TD
    Start[Running Airflow in production?] --> Q1{On AWS or GCP?}
    Q1 -->|AWS| Q2{Want full control?}
    Q1 -->|GCP| Composer[Cloud Composer 2]
    Q1 -->|Either or multi-cloud| EKS[Self-managed on EKS/GKE]
    Q2 -->|Yes - we manage k8s| EKS
    Q2 -->|No - just give me Airflow| MWAA[Amazon MWAA]
    EKS --> Note1[Latest Airflow version, full config access]
    MWAA --> Note2[Managed, but version lag and less flexibility]
    Composer --> Note3[Best for BigQuery-heavy data stacks]
```

---

## Cost Quick Guide

| Option | Rough Monthly Cost (small env) | Who manages infra? |
|--------|-------------------------------|-------------------|
| EKS self-managed | $150–300 (EKS + nodes) | You |
| MWAA mw1.small | ~$320 | AWS |
| Cloud Composer 2 | ~$300–500 | Google |

*Costs vary significantly by region, instance size, and usage.*

---

## Before You Start

- Expert Track complete (especially Custom Operators, Secrets, Performance)
- An active AWS or GCP account with billing enabled
- Familiarity with Kubernetes basics helps for the EKS module
- Budget for cloud resource costs if following along hands-on

---

<div align="center">
⬅️ [Airflow 3 Features](../05_Airflow_3_Features/Readme.md) &nbsp;|&nbsp; 🏠 [Home](../00_Learning_Guide/Readme.md) &nbsp;|&nbsp; [Integrations ➡️](../07_Integrations/Readme.md)
</div>
