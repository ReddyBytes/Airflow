# Airflow 3 Installation — Interview Q&A

## 10 Questions on Installation, Setup, and Configuration

---

**Q1. What are the steps to get Airflow 3 running with Docker Compose?**

1. Download the official Airflow 3 `docker-compose.yaml`:
   ```bash
   curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.0/docker-compose.yaml'
   ```
2. Create the required directories and `.env` file:
   ```bash
   mkdir -p ./dags ./logs ./plugins ./config
   echo -e "AIRFLOW_UID=$(id -u)" > .env
   ```
3. Run the initialization step (creates the database schema and admin user):
   ```bash
   docker compose up airflow-init
   ```
4. Start all services:
   ```bash
   docker compose up -d
   ```
5. Access the UI at **http://localhost:8080** with `admin` / `admin`.

---

**Q2. Why is Docker Compose the recommended way to run Airflow 3?**

Docker Compose is recommended for several reasons:

- **All components are pre-configured.** The `docker-compose.yaml` from the official Airflow docs wires up all services (API server, scheduler, DAG processor, workers, triggerer, PostgreSQL, Redis) with the correct environment variables, health checks, and dependencies.
- **Reproducibility.** The exact same setup runs identically on any machine with Docker installed.
- **Isolation.** All Airflow processes run in containers, so there are no conflicts with your local Python environment or system packages.
- **Easy cleanup.** `docker compose down --volumes` removes everything cleanly.

For production deployments, managed Kubernetes (via the official Helm chart) or managed Airflow services (MWAA, Cloud Composer, Astro) are typically used instead.

---

**Q3. What does `airflow db migrate` do? How is it different from the old `airflow db init`?**

`airflow db migrate` performs two jobs:
1. **First-time initialization:** If the database is empty, it creates all the required tables (`dag`, `dag_run`, `task_instance`, `xcom`, `variable`, `connection`, etc.).
2. **Schema upgrades:** If you are upgrading from an older Airflow version, it applies any new schema migrations (ALTER TABLE, new indexes, new columns) to bring the database up to the current version.

The old `airflow db init` (Airflow 2) only did first-time initialization and did not apply incremental migrations. Airflow 2 had a separate `airflow db upgrade` command for upgrades.

**Airflow 3 unifies both into `airflow db migrate`** — one command for both init and upgrade.

---

**Q4. What is `AIRFLOW_UID` and why does it matter?**

`AIRFLOW_UID` is an environment variable that tells Docker which Linux user ID to use inside the Airflow containers. It must match your local user's UID.

**Why it matters:** The `dags/`, `logs/`, and `plugins/` folders are mounted from your local machine into the containers. If the container runs as a different user ID than your local user, files written by the container (like task logs) will be owned by root or an unknown user — causing "permission denied" errors when you try to read them locally.

**Best practice:**
```bash
# Add to .env — this uses your actual user ID
echo -e "AIRFLOW_UID=$(id -u)" > .env
```

On macOS and Windows with Docker Desktop, file permissions are handled differently, so this is less critical — but it is still good practice to set it.

---

**Q5. How do you add a new DAG to Airflow 3?**

Simply save your Python DAG file in the `dags/` folder that was created during setup. The DAG Processor automatically detects and parses new files.

```bash
# With Docker Compose — dags/ is mounted as a volume
cp my_pipeline.py ./dags/

# The DAG Processor runs a continuous scan loop
# Your DAG appears in the UI within ~30 seconds by default
```

If the DAG does not appear:
1. Check for import errors: **UI → Browse → Import Errors**.
2. Check DAG Processor logs: `docker compose logs airflow-dag-processor`.
3. Verify the file is in the correct directory: the `dags_folder` config in `[core]` section.

Note: **New DAGs are paused by default.** You must toggle them on in the UI or run `airflow dags unpause <dag_id>`.

---

**Q6. What is the difference between the Airflow 3 API Server and the old Airflow 2 Webserver?**

| | Airflow 2 Webserver | Airflow 3 API Server |
|---|---|---|
| Serves Web UI | Yes | Yes |
| Serves REST API | No (separate) | Yes (same process) |
| Start command | `airflow webserver` | `airflow api-server` |
| Architecture | Stateful (session in memory) | Stateless |
| Direct DB access | Yes | No (via Internal API only) |
| Horizontal scaling | Difficult | Easy (stateless, behind LB) |

The API Server is stateless, meaning you can run multiple instances behind a load balancer without sticky sessions. Any instance can serve any request.

---

**Q7. What Airflow 3 commands do you need to start on a bare-metal install?**

On a bare-metal (non-Docker) Airflow 3 install, you need to start these processes separately:

```bash
airflow api-server      # Web UI + REST API (replaces 'airflow webserver')
airflow scheduler       # Task scheduling loop
airflow dag-processor   # DAG file parsing (NEW — separate in v3)
airflow triggerer        # Async trigger handling (for deferrable operators)
airflow celery worker   # Only if using CeleryExecutor
```

A common mistake is forgetting `airflow dag-processor`. Without it, no DAGs will be parsed or appear in the UI, even if the files are in the right folder. The Scheduler no longer does this job in Airflow 3.

---

**Q8. What is the `airflow-init` service in Docker Compose and what does it do?**

`airflow-init` is a one-time setup service defined in the Airflow 3 `docker-compose.yaml`. It:

1. Waits for PostgreSQL and Redis to be healthy.
2. Runs `airflow db migrate` to create/update the database schema.
3. Creates the default admin user (username: `admin`, password: `admin` by default, or values from `_AIRFLOW_WWW_USER_USERNAME` and `_AIRFLOW_WWW_USER_PASSWORD` env vars).
4. Checks system requirements (RAM, Python version, etc.).
5. **Exits with code 0** when done.

It is not a persistent service — it runs, does its setup work, and stops. The other services (`airflow-apiserver`, `airflow-scheduler`, etc.) have a dependency on `airflow-init` completing successfully before they start.

---

**Q9. How do you install additional Python packages in a Docker Compose Airflow 3 setup?**

The recommended approach is to create a custom Docker image that extends the official Airflow image:

```dockerfile
# Dockerfile
FROM apache/airflow:3.0.0
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

```
# requirements.txt
pandas==2.0.0
boto3
scikit-learn
```

Then update `docker-compose.yaml` to build your image instead of pulling the official one:

```yaml
# In docker-compose.yaml, change:
# image: ${AIRFLOW_IMAGE_NAME:-apache/airflow:3.0.0}
# to:
build: .
```

Finally:
```bash
docker compose build
docker compose up -d
```

An alternative is to use the `_PIP_ADDITIONAL_REQUIREMENTS` environment variable for quick testing (not recommended for production because it installs packages on every container start):

```yaml
environment:
  _PIP_ADDITIONAL_REQUIREMENTS: "pandas boto3"
```

---

**Q10. What are the main differences between LocalExecutor and CeleryExecutor, and which should you use when learning?**

| | LocalExecutor | CeleryExecutor |
|---|---|---|
| Task execution | Subprocesses on same machine | Separate worker machines |
| Message broker | Not needed | Required (Redis or RabbitMQ) |
| Multi-node | No | Yes |
| Setup complexity | Simple | More complex |
| Best for | Development, small workloads, learning | Production, high-parallelism workloads |

**For learning:** Start with `LocalExecutor`. It requires only PostgreSQL (no Redis, no separate worker nodes), making setup much simpler. The Docker Compose file from the official docs defaults to `CeleryExecutor` to demonstrate a production-like setup, but you can switch to `LocalExecutor` by changing one environment variable:

```yaml
AIRFLOW__CORE__EXECUTOR: LocalExecutor
```

And removing the `redis`, `airflow-worker`, and `flower` services from `docker-compose.yaml`.
