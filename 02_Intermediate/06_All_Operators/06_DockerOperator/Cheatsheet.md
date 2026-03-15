# DockerOperator — Cheatsheet

> Quick reference for Apache Airflow 3. Provider: `apache-airflow-providers-docker`

---

## Install

```bash
pip install apache-airflow-providers-docker
```

---

## Import

```python
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount, Resources
```

---

## Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image` | `str` | required | Docker image to run, e.g. `"python:3.11-slim"` |
| `command` | `str \| list` | `None` | Command to run in the container (overrides image CMD) |
| `environment` | `dict` | `None` | Environment variables passed to the container |
| `mounts` | `list[Mount]` | `None` | Volume mounts using `docker.types.Mount` objects |
| `volumes` | `list[str]` | `None` | Legacy volume syntax: `["/host/path:/container/path:rw"]` |
| `docker_url` | `str` | `unix:///var/run/docker.sock` | Docker daemon URL |
| `docker_conn_id` | `str` | `None` | Airflow Connection for Docker registry auth |
| `network_mode` | `str` | `"bridge"` | Docker network mode |
| `auto_remove` | `str` | `"success"` | Remove container after exit: `"success"`, `"force"`, `"never"` |
| `xcom_push` | `bool` | `False` | Push last stdout line to XCom |
| `container_resources` | `Resources` | `None` | CPU/memory limits via `docker.types.Resources` |
| `force_pull` | `bool` | `False` | Always pull image even if present locally |
| `tls_ca_cert` | `str` | `None` | TLS CA cert path for remote Docker |
| `working_dir` | `str` | `None` | Working directory inside the container |
| `entrypoint` | `str \| list` | `None` | Override container ENTRYPOINT |
| `mem_limit` | `str` | `None` | Legacy memory limit, e.g. `"4g"` |
| `cpus` | `float` | `None` | Legacy CPU limit, e.g. `0.5` |

---

## Code Patterns

### Basic Container Run

```python
from airflow.providers.docker.operators.docker import DockerOperator

run_script = DockerOperator(
    task_id="run_etl",
    image="myrepo/etl:v1.2.3",
    command="python etl.py --date {{ ds }}",
    auto_remove="force",
)
```

### With Environment Variables

```python
from airflow.models import Variable

DockerOperator(
    task_id="train_model",
    image="myrepo/trainer:latest",
    command="python train.py",
    environment={
        "RUN_DATE": "{{ ds }}",
        "DB_HOST": "postgres.internal",
        "DB_PASSWORD": Variable.get("db_password"),
        "EPOCHS": "50",
    },
    auto_remove="force",
)
```

### With Volume Mounts

```python
from docker.types import Mount

DockerOperator(
    task_id="process_files",
    image="myrepo/processor:latest",
    command="python process.py",
    mounts=[
        Mount(source="/data/input",  target="/app/input",  type="bind"),
        Mount(source="/data/output", target="/app/output", type="bind"),
    ],
    auto_remove="success",
)
```

### With Resource Limits

```python
from docker.types import Resources

DockerOperator(
    task_id="heavy_job",
    image="myrepo/heavy:latest",
    command="python heavy_compute.py",
    container_resources=Resources(
        mem_limit="8g",
        cpu_quota=400000,    # 4 CPUs (microseconds per 100ms)
    ),
    auto_remove="force",
)
```

### Capture Output via XCom

```python
# Container script must print result as the LAST line of stdout:
# print(json.dumps({"rows_processed": 1234}))

DockerOperator(
    task_id="count_rows",
    image="myrepo/counter:latest",
    command="python count.py",
    xcom_push=True,
    auto_remove="force",
)
# Downstream:
# result = ti.xcom_pull(task_ids="count_rows")  # '{"rows_processed": 1234}'
```

### Private Registry with Auth

```python
DockerOperator(
    task_id="run_private",
    image="myprivateregistry.com/myimage:v1",
    docker_conn_id="my_docker_registry",   # Airflow Connection (type: Docker)
    command="python run.py",
    auto_remove="force",
)
```

### Remote Docker Host

```python
DockerOperator(
    task_id="run_remote",
    image="myrepo/job:latest",
    docker_url="tcp://docker-host.internal:2375",
    command="python job.py",
    network_mode="my_network",
    auto_remove="force",
)
```

---

## DockerOperator vs KubernetesPodOperator

| Dimension | DockerOperator | KubernetesPodOperator |
|-----------|---------------|-----------------------|
| Infrastructure needed | Docker daemon | Kubernetes cluster |
| Production scalability | Single host only | Cluster autoscaling |
| Resource limits | Docker API | K8s requests/limits |
| Secret management | Env vars / Docker secrets | Kubernetes Secrets natively |
| Network isolation | Docker networks | K8s namespaces + NetworkPolicy |
| Sidecar containers | No | Yes (init containers, sidecars) |
| Cloud-native integration | Limited | Full (IAM, PVC, ConfigMap) |
| Local dev experience | Excellent | Requires minikube/kind |
| Setup complexity | Low | High |
| Recommended for production | Only small/single-node | Yes |

---

## When to Use DockerOperator

- Local development and testing of containerised tasks.
- Single-node Airflow deployments where Kubernetes is unavailable.
- Running non-Python tasks (R, Java, Node.js) in isolated environments.
- Reusing existing Docker images without modification.

## When to Avoid DockerOperator

- Production workloads that need autoscaling across multiple nodes.
- When the Docker socket (`/var/run/docker.sock`) cannot be exposed for security reasons.
- When you need native Kubernetes secrets, ConfigMaps, or PersistentVolumeClaims.
- When running on managed Airflow services (Astro, Google Cloud Composer) that do not support Docker socket access.

---

## XCom Limitations

DockerOperator XCom works by capturing the **last line of stdout only**. Constraints:
- Output must be a string (serialize with `json.dumps` for structured data).
- Not suitable for large payloads — use S3/GCS and push only the path.
- If the container exits with no stdout, XCom value is `None`.

---

## Golden Rules

1. Always pin image tags (`v1.2.3`) — never use `latest` in production.
2. Set `auto_remove="force"` in production to prevent container accumulation.
3. Use `mounts` (not `volumes`) for new code — `volumes` is the legacy API.
4. Never hardcode secrets in `environment` — use Airflow Variables or Secrets Backend.
5. Set `container_resources` limits — an unconstrained container can starve the host.
6. Keep XCom output small — write large results to object storage, push the path.
7. Use `"never"` `auto_remove` only temporarily during debugging.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev operator** | [05_HttpOperator](../05_HttpOperator/) |
| **Next operator** | [07_KubernetesPodOperator](../07_KubernetesPodOperator/) |
| **Section root** | [02_Intermediate](../../) |
