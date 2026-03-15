# EdgeExecutor — Interview Q&A

> Study guide for Apache Airflow 3. EdgeExecutor is new in Airflow 3 — it does not exist in Airflow 2.x.

---

## Q1: What is EdgeExecutor and what problem does it solve?

**Answer:**

`EdgeExecutor` is a new executor introduced in **Apache Airflow 3** designed to orchestrate tasks on **remote, resource-constrained, or intermittently connected machines** — devices and environments where traditional Airflow executors (Celery, Kubernetes) are impractical.

The problem it solves: you want centralised Airflow orchestration, but you need tasks to run on machines that:
- Are far from the central data centre (retail stores, factory floors, remote field stations)
- Have limited resources — no Docker, no Kubernetes, minimal RAM and CPU
- Have unreliable or intermittent internet connectivity
- May be behind corporate firewalls that only allow outbound HTTPS

CeleryExecutor requires a persistent connection to a Redis/RabbitMQ broker. KubernetesExecutor requires a Kubernetes cluster. Neither works in these scenarios. EdgeExecutor uses simple **HTTP polling** — the remote worker periodically calls the central Airflow API to ask "do you have any tasks for me?" No persistent connection, no broker, no Kubernetes.

---

## Q2: How does EdgeExecutor work architecturally?

**Answer:**

The architecture has two sides:

**Central Airflow** (cloud or data centre):
- Runs the scheduler, webserver, and metadata database as usual
- The scheduler places ready tasks into queues in the metadata DB
- The webserver exposes an API endpoint that edge workers poll

**Edge Workers** (remote machines):
- Lightweight Python processes running the `airflow edge worker` command
- Periodically poll the central Airflow REST API (every 10 seconds by default): "Is there a task in my queue?"
- When a task is returned, the edge worker runs it locally as a subprocess
- When the task completes, the worker POSTs the result (success/failure + logs) back to the API
- If connectivity drops mid-task, the task keeps running locally. Results sync when connectivity resumes.

Key design choice: **HTTP polling, not push**. The edge worker initiates all communication. This makes it work through NAT, firewalls, and VPNs without opening inbound ports on edge machines.

---

## Q3: How does EdgeExecutor differ from CeleryExecutor?

**Answer:**

| Aspect | CeleryExecutor | EdgeExecutor |
|---|---|---|
| Communication model | Worker pulls from broker queue | Worker polls central HTTP API |
| Broker required | Yes (Redis or RabbitMQ) | No |
| Network requirement | Persistent connection to broker | Intermittent HTTPS is fine |
| Worker footprint | Full Celery + Airflow installation | Minimal (`apache-airflow[edge]`) |
| Offline task execution | No — tasks fail if broker unreachable | Yes — tasks continue locally |
| Target environment | Dedicated worker servers | Edge devices, IoT, remote sites |
| Scalability | Horizontal — add more workers | Per-site — each site has its own worker |
| Worker discovery | Via broker subscription | Via worker registration + token |

The fundamental difference is connectivity model: Celery workers **need** a reliable broker connection; edge workers only need **occasional** HTTPS access to the central API.

---

## Q4: What are typical edge computing use cases for EdgeExecutor?

**Answer:**

| Industry | Use Case |
|---|---|
| **Retail** | Per-store end-of-day reconciliation, inventory sync, POS data aggregation |
| **Manufacturing** | Factory-floor quality control checks, sensor data validation, equipment monitoring |
| **IoT / Utilities** | Edge processing of sensor streams (temperature, pressure, flow), meter reading |
| **Healthcare** | On-premise data processing for HIPAA compliance — only anonymised results leave the site |
| **Field Operations** | Remote site monitoring (oil wells, weather stations) via satellite or 4G |
| **Financial Services** | Branch office pre-processing before central consolidation |
| **Logistics** | Warehouse automation, dock door scheduling, shipment reconciliation |

The common thread: data must be processed close to where it is generated, with only results or aggregates sent to the central system — either for latency reasons, bandwidth constraints, or regulatory compliance.

---

## Q5: How do you set up an edge worker and register it with the central Airflow?

**Answer:**

Step 1 — On the **central Airflow**, generate an authentication token for the new worker:

```bash
airflow edge worker create-token --worker-name store-001
# Returns a JWT token — copy this securely
```

Step 2 — On the **edge machine**, install the Airflow edge package:

```bash
pip install "apache-airflow[edge]>=3.0.0"
```

Step 3 — Start the edge worker on the edge machine:

```bash
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGci... \
  --queue store-001
```

Step 4 — Verify the worker is registered:

```bash
# On central Airflow
airflow edge worker list
```

The worker is now polling the central API for tasks in the `store-001` queue. Any task with `queue="store-001"` will be delivered to this worker.

---

## Q6: How do you route specific tasks to specific edge workers?

**Answer:**

Routing uses **Celery-style queue assignment**. Each edge worker listens on one or more named queues. Tasks are assigned to queues in the DAG code.

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id="multi_site_pipeline",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
)
def multi_site_pipeline():

    @task(queue="store-001")   # → runs on edge worker at store 001
    def reconcile_store_001():
        pass

    @task(queue="store-002")   # → runs on edge worker at store 002
    def reconcile_store_002():
        pass

    @task  # No queue = default queue = runs on central Airflow
    def aggregate_results():
        pass

    r1 = reconcile_store_001()
    r2 = reconcile_store_002()
    [r1, r2] >> aggregate_results()
```

If a task's queue does not match any registered edge worker, the task waits indefinitely. Use the Airflow UI or `airflow edge worker list` to verify worker queues.

---

## Q7: What happens if the edge worker loses connectivity mid-task?

**Answer:**

EdgeExecutor is designed for exactly this scenario:

- **Task in progress when connectivity drops**: the edge worker continues executing the task locally. The task does not fail — it runs to completion.
- **Result sync**: when connectivity is restored, the worker sends the task result (success/failure, logs) to the central API.
- **Tasks not yet fetched**: they remain in the queue on the central Airflow instance. They are delivered to the edge worker once it reconnects and resumes polling.
- **Worker heartbeat timeout**: if the worker is offline longer than `worker_timeout` seconds (default: 120), the central Airflow marks the worker as "offline." Tasks queued for that worker remain queued — they are not automatically reassigned unless you configure a fallback.

This graceful offline behaviour is the primary reason to use EdgeExecutor over CeleryExecutor for intermittently connected sites.

---

## Q8: What network connectivity does EdgeExecutor require?

**Answer:**

EdgeExecutor requires only:
- **Outbound HTTPS** from the edge machine to the central Airflow webserver API
- A valid **authentication token** in the HTTP request header

It does NOT require:
- Inbound connections to the edge machine (no port forwarding needed)
- Persistent TCP connections (a failed HTTP poll is retried next interval)
- Low-latency connectivity (a 30-second poll interval is fine on slow links)
- A VPN, though HTTPS over a VPN adds security

This minimal network requirement is what makes EdgeExecutor work on 4G/LTE links, satellite connections, store broadband, or intermittent Wi-Fi.

---

## Q9: How does EdgeExecutor handle DAG file distribution to edge workers?

**Answer:**

Edge workers need access to the DAG files to execute tasks — but they do not run the Airflow scheduler or webserver, so there is no automatic DAG sync built in.

Common approaches:

1. **Git clone/pull**: configure a cron job or systemd timer on the edge machine to `git pull` the DAG repo at regular intervals.
2. **rsync from central**: a central job syncs DAG files to edge machines over SSH.
3. **Edge machine holds local DAG copies**: for edge use cases, DAG files are often simple and rarely change — keeping a local copy and syncing on deployment is practical.
4. **Package DAGs into the edge worker's Python package**: for stable, infrequently-changing DAGs, bake them into the pip package installed on edge machines.

The official recommendation for production: use Git-based sync so edge machines always run the latest DAG code.

---

## Q10: How is EdgeExecutor different from just running a standalone Airflow instance at each edge site?

**Answer:**

You could run a full, independent Airflow instance at each edge site — but EdgeExecutor offers significant advantages:

| Aspect | Standalone Airflow per Site | EdgeExecutor |
|---|---|---|
| Centralised visibility | No — each site is isolated | Yes — all edge tasks visible in one UI |
| Infrastructure per site | Full Airflow stack (scheduler, webserver, DB) | Just the lightweight edge worker binary |
| DAG management | Deploy DAG changes to every site separately | One central deployment, edge workers pick up tasks |
| Resource requirements | Significant (PostgreSQL, multiple services) | Minimal (single Python process) |
| Monitoring | Multiple dashboards | Single central Airflow UI |
| Cost | High (running N full Airflow stacks) | Low (N lightweight worker processes) |

EdgeExecutor gives you **centralised orchestration with distributed execution** — the best of both worlds for edge scenarios.

---

## Q11: What are the limitations of EdgeExecutor?

**Answer:**

EdgeExecutor is new in Airflow 3 and has some important limitations to know:

1. **Airflow 3 only**: does not exist in Airflow 2.x.
2. **DAG files must be present on edge machines**: Airflow does not automatically distribute DAGs to edge workers.
3. **No Airflow UI on the edge machine**: the edge worker has no local web interface. All monitoring is via the central Airflow UI.
4. **Not for high throughput**: designed for low-to-moderate task volumes per site. For high-frequency edge tasks, consider a local Airflow with LocalExecutor.
5. **Security responsibility**: edge workers authenticate via tokens. A stolen token allows task execution — rotate tokens regularly and use HTTPS.
6. **Task isolation is subprocess-level**: like LocalExecutor, tasks on an edge worker share the same machine. There is no container isolation between tasks.
7. **Result delay**: results are sent over the network, not written directly to the DB. There is a slight delay between task completion and state update in the central metadata DB.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
