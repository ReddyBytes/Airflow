# DockerOperator — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Beginner

**Q1. What is DockerOperator and what problem does it solve?**

Imagine you have a data processing script written in R, a legacy Java ETL tool, or a Node.js transformer — none of these run natively in an Airflow Python worker. DockerOperator lets you run any container image as an Airflow task. Your DAG says "pull this Docker image, run this command, wait for it to exit" — and Airflow handles the rest. This means your pipelines are no longer constrained to Python, and each task gets an isolated, reproducible environment.

**Q2. When would you use DockerOperator?**

- Running tasks in languages other than Python (R, Java, Scala, Go).
- Isolating dependencies — task A needs NumPy 1.x, task B needs NumPy 2.x; each runs in its own container.
- Reusing existing Docker images (e.g., official database migration images, pre-built ML training images).
- Running shell scripts that require specific system tools not installed on the Airflow worker.

**Q3. What is the `image` parameter?**

`image` is the Docker image to pull and run, specified as a string in standard Docker format:

```
"python:3.11-slim"                     # official image, latest digest
"myrepo/my-etl:v1.2.3"               # private registry image with version tag
"gcr.io/myproject/trainer:latest"     # Google Container Registry
```

Airflow will `docker pull` the image before running the container. You can control whether to pull with the `force_pull` parameter.

**Q4. What is the `command` parameter?**

`command` is the command (or list of command parts) to run inside the container, overriding the image's default `CMD`. It can be a string or list:

```python
command="python train.py --epochs 10"
# or
command=["python", "train.py", "--epochs", "10"]
```

Jinja templating is supported, so you can inject execution dates or XCom values.

**Q5. What does `auto_remove` do?**

`auto_remove` (default: `"success"` in Airflow 3, `True/False` in older versions) controls whether the container is removed after it exits. Options: `"success"` (remove only on success), `"force"` (always remove), `"never"` (keep for debugging). In production, use `"success"` or `"force"` to avoid container accumulation. During debugging, use `"never"` so you can `docker logs` the container after a failure.

---

## Intermediate

**Q6. How do you pass environment variables to the container?**

Use the `environment` parameter, which accepts a plain Python dictionary:

```python
DockerOperator(
    task_id="train_model",
    image="myrepo/trainer:latest",
    command="python train.py",
    environment={
        "DB_HOST": "postgres.internal",
        "MODEL_VERSION": "{{ ds }}",           # Jinja-templated
        "API_KEY": Variable.get("api_key"),    # from Airflow Variables
    },
)
```

Secrets should come from Airflow Variables or Secrets Backend — never hardcoded in the DAG file.

**Q7. How do you mount volumes into the container?**

Use the `mounts` parameter (Airflow 3) with `docker.types.Mount` objects, or `volumes` (older API) with string syntax:

```python
from docker.types import Mount

DockerOperator(
    task_id="process_files",
    image="myrepo/processor:latest",
    command="python process.py",
    mounts=[
        Mount(source="/data/input", target="/app/input", type="bind"),
        Mount(source="/data/output", target="/app/output", type="bind"),
    ],
)
```

String syntax (legacy): `volumes=["/host/path:/container/path:ro"]`. Mounts allow the container to read input files and write output files that persist after the container exits.

**Q8. How do you capture container output?**

Two mechanisms:

1. **Logs**: DockerOperator streams `stdout` and `stderr` to Airflow task logs by default — no configuration needed.

2. **XCom output**: Set `xcom_push=True` and have your container write output to `stdout` as the last line. DockerOperator captures the last line of stdout and pushes it to XCom:

```python
DockerOperator(
    task_id="get_result",
    image="myrepo/script:latest",
    command="python compute.py",    # script prints result as last stdout line
    xcom_push=True,
)
# script.py: print(json.dumps({"result": 42}))
```

Then downstream: `ti.xcom_pull(task_ids="get_result")` returns `'{"result": 42}'`.

**Q9. How do you connect to a Docker daemon that is not on localhost?**

Use `docker_url` to point to a remote Docker socket or TCP endpoint:

```python
DockerOperator(
    task_id="run_container",
    image="myrepo/job:latest",
    docker_url="tcp://docker-host:2376",    # remote Docker engine
    # or for TLS:
    docker_url="tcp://docker-host:2376",
    tls_ca_cert="/certs/ca.pem",
    tls_client_cert="/certs/cert.pem",
    tls_client_key="/certs/key.pem",
)
```

On a local development machine, the default `unix:///var/run/docker.sock` works if Airflow runs on the same host as Docker.

**Q10. What is `network_mode` and when do you need it?**

`network_mode` sets the Docker network for the container. Useful cases:

| Mode | When to use |
|------|-------------|
| `"bridge"` (default) | Standard container networking |
| `"host"` | Container shares host network (not portable) |
| `"container:<id>"` | Join another container's network |
| `"<custom_network>"` | Connect to a named Docker network (e.g., to reach other services) |

If your container needs to call another service (e.g., a database) on the same Docker network, set `network_mode="my_docker_network"`.

---

## Advanced

**Q11. DockerOperator vs KubernetesPodOperator — when to choose each?**

| Dimension | DockerOperator | KubernetesPodOperator |
|-----------|---------------|-----------------------|
| Infrastructure | Docker daemon on a single host | Kubernetes cluster |
| Scaling | Limited to one host's resources | Cluster-level autoscaling |
| Isolation | Container-level | Pod-level (can include sidecars) |
| Resource limits | Via Docker API | Kubernetes resource requests/limits |
| Secret management | Docker secrets / env vars | Kubernetes Secrets natively |
| Production at scale | Not recommended | Preferred for production |
| Local development | Excellent | Requires local K8s (minikube) |
| Overhead | Low | Higher (pod scheduling) |

Choose DockerOperator for local development and single-node setups. Use KubernetesPodOperator for cloud-native, production workloads that need scaling and native K8s secret integration.

**Q12. How do you pass XCom data from a Docker container back to Airflow?**

XCom from DockerOperator is limited to the last line of `stdout`. This means:

1. Your container script must print the XCom payload as the last `print()` call.
2. The payload is a string — serialize complex objects with `json.dumps()`.
3. Set `xcom_push=True` on the operator.

For large outputs, the pattern breaks down — XCom is stored in the Airflow metadata DB and is not designed for large data. In that case, write output to an external store (S3, GCS, database) and push only the reference (a path or ID) via XCom.

**Q13. When is DockerOperator a bad idea in production?**

- **Single point of failure**: All containers run on the Docker host where the Airflow worker is — if the host goes down, everything stops.
- **No autoscaling**: You cannot scale Docker containers across a fleet of machines easily.
- **Resource contention**: Many parallel tasks compete for CPU/RAM on the same host.
- **Docker socket access is a security risk**: Mounting `/var/run/docker.sock` into the Airflow worker gives container-level root access to the host.
- **Not cloud-native**: No integration with cloud IAM, secret managers, or managed container services.

For production at scale, KubernetesPodOperator or EcsOperator (AWS) is almost always the better choice.

**Q14. How do you handle Docker image registry authentication?**

Two options:

1. **Pre-authenticate on the Docker host**: Run `docker login` on the machine running Airflow before starting the scheduler/workers.

2. **Pass credentials via `DockerOperator`**: Use the `docker_conn_id` parameter pointing to an Airflow Connection of type `Docker` that stores registry credentials. Airflow will authenticate before pulling the image.

```python
DockerOperator(
    task_id="run_private_image",
    image="myprivateregistry.com/myimage:v1",
    docker_conn_id="my_docker_registry",    # Airflow Connection
)
```

**Q15. How do you set resource limits (CPU, memory) on containers?**

Use the `container_resources` parameter (Airflow 3) with a `docker.types.Resources` object:

```python
from docker.types import Resources

DockerOperator(
    task_id="heavy_job",
    image="myrepo/heavy:latest",
    container_resources=Resources(
        mem_limit="4g",          # 4 GB RAM limit
        cpu_quota=200000,        # 2 CPUs (in microseconds per 100ms period)
    ),
)
```

Without limits, a runaway container can consume all host resources and starve other tasks.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Prev operator** | [05_HttpOperator](../05_HttpOperator/) |
| **Next operator** | [07_KubernetesPodOperator](../07_KubernetesPodOperator/) |
| **Section root** | [02_Intermediate](../../) |
