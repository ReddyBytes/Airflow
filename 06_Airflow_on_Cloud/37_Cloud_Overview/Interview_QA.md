# Cloud Overview — Interview Q&A

Questions that come up when discussing Airflow deployment strategy in data engineering
and platform engineering interviews.

---

## Q1. What are the three main ways to run Airflow in production, and how do they differ?

**Answer:**

1. **Self-managed on Kubernetes (EKS/GKE/AKS)** — You install Airflow using the official
   Helm chart on a cluster you control. You get the latest Airflow version, full config
   access, and any executor. You own all infrastructure operations.

2. **Amazon MWAA** — AWS runs Airflow for you. Low operational overhead, native AWS IAM
   integration, but limited to CeleryExecutor and 1–2 versions behind open source.

3. **Google Cloud Composer** — GCP runs Airflow on managed GKE. Best for GCP-heavy
   stacks. Uses KubernetesExecutor internally, good Workload Identity support.

The core trade-off: **control vs operational overhead**.

---

## Q2. When would you choose MWAA over self-managed Airflow on EKS?

**Answer:**
Choose MWAA when:
- Your data stack is heavily AWS (S3, Redshift, Glue, EMR) and you want native IAM integration
- You don't have a Kubernetes team to own the cluster
- Operational simplicity matters more than configuration flexibility
- CeleryExecutor is sufficient for your workloads
- You can accept Airflow being 1–2 minor versions behind open source

Avoid MWAA when you need KubernetesExecutor, custom executors, latest Airflow 3 features,
or aggressive cost optimisation via Spot instances.

---

## Q3. What are the cost trade-offs between managed and self-managed Airflow?

**Answer:**
Counter-intuitively, self-managed can be cheaper at scale but more expensive for small teams:

| Deployment | ~Monthly Cost | Hidden cost |
|---|---|---|
| Self-managed EKS | $150–250 (compute) | Engineering time to operate |
| MWAA (mw1.small) | $320–380 | None — it's all-in |
| Cloud Composer 2 | $300–500 | None — it's all-in |

Self-managed is cheaper on **compute** but carries an operational overhead cost — someone
must manage Kubernetes upgrades, Airflow upgrades, scaling, and on-call. For teams
without a dedicated platform engineer, managed is often cheaper overall.

---

## Q4. How portable are Airflow DAGs between deployment options?

**Answer:**
DAG **code** is highly portable — a DAG written for local Docker Compose will run on
MWAA, Cloud Composer, or EKS with minimal changes.

What is NOT portable:
- **Connections** — format and storage differ (Airflow UI, Secrets Manager, environment variables)
- **DAG deployment method** — GitSync vs S3 bucket vs GCS bucket vs image bake
- **Provider packages** — some providers are pre-installed by managed services
- **Infrastructure config** — `values.yaml` (EKS), environment settings (MWAA), `gcloud` config (Composer)

**Rule:** Plan for a connection reconfiguration step when migrating between deployment options.

---

## Q5. What is version lag and why does it matter for MWAA and Cloud Composer?

**Answer:**
Managed services take time to validate and release new Airflow versions. MWAA and Cloud
Composer typically support versions that are 1–2 minor versions behind the open source release.

Why it matters:
- Airflow 3 introduced breaking changes (Assets replacing Datasets, new UI, new scheduler)
- If you need Airflow 3 features on day one, you must self-manage
- Bug fixes and security patches in newer versions aren't available until the managed service
  updates

If your team relies on bleeding-edge Airflow features, self-managed EKS or GKE is the
only path.

---

## Q6. What operational responsibilities do you take on with self-managed Airflow?

**Answer:**
You own:
- **Kubernetes cluster** — node upgrades, security patches, scaling
- **Airflow upgrades** — testing compatibility, running migration scripts (`airflow db migrate`)
- **Metadata database** — RDS backups, version upgrades, connection pool tuning
- **Worker scaling** — configuring KEDA or HPA for dynamic task load
- **Log storage** — S3/GCS bucket setup, retention policies
- **On-call** — paging when the scheduler crashes at 3am

This is why teams without a dedicated platform engineer typically prefer managed services.

---

## Q7. How do you handle Python package installation in each deployment option?

**Answer:**

| Option | How to add packages |
|---|---|
| Self-managed | Add to `requirements.txt` in your Docker image, rebuild and redeploy |
| MWAA | Upload `requirements.txt` to S3 alongside your DAGs — MWAA installs on environment update |
| Cloud Composer | Upload `requirements.txt` to the GCS bucket — Composer installs automatically |

Self-managed gives you the most control (you can pin exact versions and test the image
locally). MWAA has a size limit on the environment and takes time to rebuild. Composer
is similar to MWAA.

---

## Q8. Walk me through how you would migrate Airflow from local Docker Compose to production.

**Answer:**

1. **Choose deployment target** based on cloud provider, team k8s skills, and budget
2. **Extract connections and variables** — export from local Airflow, reformat for target
3. **Set up infrastructure** — EKS cluster + RDS, or MWAA environment, or Composer env
4. **Configure DAG deployment** — GitSync, S3, or GCS depending on target
5. **Test with a subset of DAGs** — verify task execution, logs, and connections
6. **Migrate all DAGs** and run parallel for a short period to validate outputs match
7. **Decommission local setup**

The biggest risk is connection misconfiguration — allocate time to verify every connection
in the new environment before cutting over.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Next: AWS EKS** | [38_AWS_EKS/Theory.md](../38_AWS_EKS/Theory.md) |
| **Next: MWAA** | [39_MWAA/Theory.md](../39_MWAA/Theory.md) |
| **Next: GCP Composer** | [40_GCP_Composer/Theory.md](../40_GCP_Composer/Theory.md) |
