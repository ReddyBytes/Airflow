# Amazon MWAA — Interview Q&A

These questions target roles involving AWS-native data pipelines where MWAA is
the chosen orchestration platform.

---

## Q1. What is Amazon MWAA and what problem does it solve?

**Answer:**
MWAA (Managed Workflows for Apache Airflow) is a fully managed service that runs
Apache Airflow on AWS. It removes the operational burden of:

- Installing and upgrading Airflow
- Managing the metadata database (Aurora Postgres behind the scenes)
- Scaling workers (auto-scaling via CeleryExecutor)
- Securing the webserver (IAM-authenticated, no password management)
- Shipping logs (CloudWatch integration built-in)

The trade-off is reduced flexibility: you cannot choose the executor, you cannot
install arbitrary system packages, and you are on AWS's version upgrade schedule.

---

## Q2. How do you deploy DAGs to MWAA?

**Answer:**
MWAA polls an S3 prefix (e.g., `s3://my-bucket/dags/`) every ~30 seconds. To deploy:

```bash
# Single file
aws s3 cp my_dag.py s3://my-mwaa-bucket/dags/

# Entire folder
aws s3 sync ./dags/ s3://my-mwaa-bucket/dags/ --delete
```

There is no restart required — the scheduler picks up new or changed DAGs
automatically within the polling interval.

For CI/CD, a GitHub Actions step after merging to `main` typically runs `aws s3 sync`.

---

## Q3. How do you install Python packages in MWAA?

**Answer:**
Upload a `requirements.txt` file to S3 and tell MWAA where to find it:

```bash
# requirements.txt
apache-airflow-providers-snowflake==4.5.0
pandas==2.1.4
great-expectations==0.18.12

# Upload
aws s3 cp requirements.txt s3://my-mwaa-bucket/requirements.txt

# Update environment to use new version
OBJECT_VERSION=$(aws s3api head-object \
  --bucket my-mwaa-bucket \
  --key requirements.txt \
  --query 'VersionId' --output text)

aws mwaa update-environment \
  --name my-env \
  --requirements-s3-object-version $OBJECT_VERSION
```

Installing packages triggers an environment update that takes 10–20 minutes.
MWAA installs packages in a constrained environment — test with `pip install --constraint
https://raw.githubusercontent.com/apache/airflow/constraints-2.10.3/constraints-3.11.txt`
locally to catch conflicts before uploading.

---

## Q4. How do you install custom plugins in MWAA?

**Answer:**
Plugins are bundled into a `plugins.zip` file:

```
plugins/
├── __init__.py
├── my_hook.py
├── my_operator.py
└── sensors/
    └── my_sensor.py
```

```bash
zip -r plugins.zip plugins/
aws s3 cp plugins.zip s3://my-mwaa-bucket/plugins.zip
# Then update environment with the new S3 version ID
```

Plugins are available to import directly: `from my_operator import MyOperator`.

Limitations: no compiled binaries (`.so` files), no packages requiring system-level
libraries (use KubernetesPodOperator via EKS for those).

---

## Q5. How does MWAA handle IAM permissions for tasks?

**Answer:**
Every MWAA worker assumes the **Execution Role** — an IAM role you specify at
environment creation time. When a task needs to access S3, call a Lambda, or read
from Secrets Manager, it uses the credentials from that role.

In practice:
- Attach a managed policy (`AmazonS3FullAccess`) or a custom inline policy to the role.
- DAG code uses `boto3` or Airflow providers — both automatically pick up the role
  credentials from the EC2 instance metadata.
- No need to store `AWS_ACCESS_KEY_ID` anywhere.

For fine-grained control, use Airflow connections that reference AWS profiles, or
use `AssumeRole` within a task to switch to a different role.

---

## Q6. What executor does MWAA use and what does that mean for task isolation?

**Answer:**
MWAA uses **CeleryExecutor** exclusively. This means:

- Tasks run as processes inside shared worker EC2 instances (not isolated pods).
- All tasks on a worker share the same Python environment, the same packages,
  and the same filesystem.
- A memory leak or infinite loop in one task can affect other tasks on the same worker.

If you need task isolation, you must use the `KubernetesPodOperator` pointing to
an EKS cluster — this lets tasks run in separate containers while MWAA handles
scheduling.

---

## Q7. How does MWAA auto-scaling work?

**Answer:**
MWAA uses AWS Application Auto Scaling on the Celery worker pool:

1. Tasks enter the Celery queue (backed by SQS in MWAA).
2. MWAA monitors queue depth.
3. Workers scale out (up to `max_workers`) when the queue grows.
4. Workers scale in (down to `min_workers`) when the queue drains.

Scale-out typically takes 2–3 minutes (EC2 launch + Airflow worker startup).
This cold-start latency means MWAA is not ideal for latency-sensitive pipelines
that need sub-minute task start times.

---

## Q8. How is MWAA priced?

**Answer:**
MWAA pricing has two components:

1. **Environment fee**: charged per hour the environment is running, regardless of
   whether any DAGs are executing. Varies by environment class (~$0.49–$6.00/hr for
   `mw1.small` to `mw1.2xlarge` in us-east-1).

2. **Worker instance time**: charged per worker-hour when workers are active. Uses
   standard EC2 pricing for the underlying instance type.

Minimum cost is the environment fee even with zero workers active, which makes
MWAA relatively expensive for dev/test environments that are idle most of the time.
For idle environments, some teams use scheduled start/stop via AWS Lambda.

---

## Q9. What are the main limitations of MWAA?

**Answer:**

| Limitation | Impact |
|---|---|
| CeleryExecutor only | No per-task pod isolation |
| Max 25 workers | Cannot burst higher |
| No KubernetesExecutor | Cannot run GPU tasks natively |
| Package install takes 10–20 min | Slow iteration on dependencies |
| AWS controls version upgrades | May be behind GA for months |
| Private subnets required | More complex VPC setup |
| No SSH access to workers | Debugging is harder |
| 1 GB plugins.zip limit | Restricts large custom libraries |

---

## Q10. How do you access Secrets Manager from MWAA?

**Answer:**
Configure the Secrets Manager backend in `airflow_configuration_options`:

```python
# In environment config (Terraform example)
airflow_configuration_options = {
  "secrets.backend" = "airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend"
  "secrets.backend_kwargs" = jsonencode({
    connections_prefix = "airflow/connections"
    variables_prefix   = "airflow/variables"
    full_url_mode      = false
  })
}
```

Then store secrets:
```bash
aws secretsmanager create-secret \
  --name airflow/connections/snowflake_default \
  --secret-string "snowflake://user:pass@account/db?warehouse=WH"
```

Airflow resolves `snowflake_default` at runtime by calling Secrets Manager.
The execution role must have `secretsmanager:GetSecretValue` permission.

---

## Q11. Compare MWAA, EKS self-managed, and GCP Cloud Composer.

**Answer:**

| Feature | MWAA | EKS | Cloud Composer |
|---|---|---|---|
| Cloud | AWS | AWS | GCP |
| Managed | Fully | No | Fully |
| Executor | Celery | Any | Celery (Composer 1), K8s (Composer 2) |
| Version lag | Weeks | None | Weeks |
| Autoscaling | Worker-level | Pod-level (KEDA/Karpenter) | Node pool + Composer 2 autoscaling |
| Custom images | No | Yes | No (but env customisation) |
| DAG store | S3 | Git/S3/Image | GCS |
| Min monthly cost | ~$350 | ~$150 | ~$300 |

**MWAA** is the natural choice if you are AWS-native and want zero ops.
**EKS** if you need KubernetesExecutor or have a platform team.
**Composer** if you are GCP-native.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Previous: EKS** | [38_AWS_EKS](../38_AWS_EKS/Theory.md) |
| **Next: GCP Composer** | [40_GCP_Composer](../40_GCP_Composer/Theory.md) |
| **Parent: Cloud** | [Cloud Overview](../37_Cloud_Overview/Theory.md) |
