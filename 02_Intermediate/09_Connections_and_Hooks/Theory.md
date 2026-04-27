# 07 — Connections and Hooks

## The Story

Imagine your DAG needs to talk to a Postgres database, an S3 bucket, and an HTTP API — but you don't want to hardcode credentials in your Python file. Maybe that file lives in version control. Maybe ten engineers share it. Maybe the password changes every 90 days.

That's what **Connections** are for.

A Connection is Airflow's **secure address book** — store credentials once, give them a name (a `conn_id`), and reference that name everywhere. Your DAG file never sees a password. You change the password in one place and every DAG that uses it picks it up automatically.

Once you have a Connection, you need something to **use** it. That's where **Hooks** come in. A Hook is the Python interface that reads a Connection and uses it to talk to the external system. The Postgres Hook knows how to open a psycopg2 connection. The S3 Hook knows how to create a boto3 session. You write simple, readable code; the Hook handles the plumbing.

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[What Is a Connection](#what-is-a-connection) · [What Is a Hook](#what-is-a-hook) · [How It All Fits Together](#how-it-all-fits-together)

**Should Learn** — important for real projects and interviews:
[How to Add a Connection](#how-to-add-a-connection) · [Hook vs Operator](#hook-vs-operator)

**Good to Know** — useful in specific situations, not needed daily:
[Connection Types](#connection-types)

---

## What Is a Connection?

A **Connection** is a named record stored in Airflow's metadata database (or a secrets backend). Each Connection has:

| Field | Purpose |
|---|---|
| `conn_id` | The unique name you reference in your DAGs (e.g., `my_postgres`) |
| `conn_type` | The category: `postgres`, `http`, `s3`, `google_cloud_platform`, etc. |
| `host` | Hostname or endpoint |
| `schema` | Database name (for DBs) or path prefix (for some cloud) |
| `login` | Username / access key ID |
| `password` | Password / secret key |
| `port` | Port number |
| `extra` | JSON for additional config (e.g., SSL settings, region) |

---

## Connection Types

Airflow ships with support for dozens of connection types. They are grouped by provider package:

| Category | Examples |
|---|---|
| **Relational databases** | `postgres`, `mysql`, `mssql`, `sqlite`, `oracle` |
| **HTTP / REST** | `http` |
| **Cloud storage** | `aws` (S3), `google_cloud_platform` (GCS, BigQuery), `azure_blob` |
| **Message queues** | `kafka`, `rabbitmq` |
| **Data warehouses** | `snowflake`, `redshift`, `bigquery` |
| **Custom** | Any type you define with a custom Hook |

Each type controls which fields are visible in the Airflow UI form, but all types ultimately store the same underlying fields.

---

## How to Add a Connection

### Method 1 — Airflow UI

Navigate to **Admin → Connections → + (Add a new record)**. Fill in the fields and save. This is the easiest approach for local development.

### Method 2 — Environment Variables

Set an environment variable before Airflow starts. Airflow reads it at runtime and treats it as a Connection. The format is a URI:

```
AIRFLOW_CONN_{CONN_ID_UPPERCASE}=<conn_type>://<login>:<password>@<host>:<port>/<schema>
```

Example:

```bash
export AIRFLOW_CONN_MY_POSTGRES=postgresql://airflow_user:secret@localhost:5432/mydb
```

This is great for containers and CI/CD pipelines — no UI, no database writes.

### Method 3 — Secrets Backend

For production you store credentials in a dedicated secrets manager (AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager). Airflow's **Secrets Backend** interface lets it look up connections there first before checking the metadata DB. This keeps credentials out of Airflow's database entirely.

---

## What Is a Hook?

A **Hook** is a Python class that:

1. Reads a Connection by `conn_id`
2. Opens a connection to the external system using the credentials
3. Exposes convenient methods for working with that system

Hooks are the bridge between Airflow's connection store and your actual code. Operators are built on top of Hooks — when you use a `PostgresOperator`, it internally creates a `PostgresHook`.

### BaseHook

All Hooks extend `airflow.hooks.base.BaseHook`. The most important inherited method is:

```python
BaseHook.get_connection(conn_id)  # Returns the Connection object
```

You can also call it as a class method from anywhere in your code to inspect a connection.

### PostgresHook Example

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

hook = PostgresHook(postgres_conn_id="my_postgres")
records = hook.get_records("SELECT id, name FROM users LIMIT 10")
# records is a list of tuples: [(1, 'Alice'), (2, 'Bob'), ...]
```

### HttpHook Example

```python
from airflow.providers.http.hooks.http import HttpHook

hook = HttpHook(method="GET", http_conn_id="my_api")
response = hook.run("/v1/status", headers={"Accept": "application/json"})
data = response.json()
```

---

## How It All Fits Together

```mermaid
flowchart LR
    DAG["DAG / Task Code"]
    Hook["Hook\n(e.g. PostgresHook)"]
    ConnStore["Connection Store\n(Metadata DB or Secrets Backend)"]
    Ext["External System\n(Postgres / S3 / API)"]

    DAG -->|"instantiates with conn_id"| Hook
    Hook -->|"BaseHook.get_connection(conn_id)"| ConnStore
    ConnStore -->|"returns credentials"| Hook
    Hook -->|"opens authenticated session"| Ext
```

The DAG code only knows the `conn_id` — a simple string like `"my_postgres"`. It never touches a password.

---

## Hook vs Operator

| Concept | Level | Your responsibility |
|---|---|---|
| **Hook** | Low-level | You write the SQL / API call yourself |
| **Operator** | High-level | Operator handles the call; you just configure it |

Most operators accept a `*_conn_id` parameter that they pass straight to the underlying Hook. When you need full control (dynamic queries, custom logic) you use a `PythonOperator` and call a Hook directly inside the function.

---

## Key Takeaways

- Connections are Airflow's credential store — one place, referenced by name everywhere.
- Hooks are the Python layer that turns a Connection into live calls to external systems.
- You can store connections in the UI, as environment variables, or in a secrets backend.
- Operators are convenience wrappers built on top of Hooks.
- Your DAG code should **never** contain raw credentials.

🚀 **Apply this:** Use Hooks in a real pipeline → [Project 01 — Forex ETL Pipeline](../../09_Capstone_Projects/01_Forex_ETL_Pipeline/01_MISSION.md)
---

## Navigation

**Prev:** [06 — Sensors](../06_Sensors/Theory.md) | **Home:** [Learning Path](../00_Learning_Guide/Learning_Path.md) | **Next:** [08 — Variables and Config](../08_Variables_and_Config/Theory.md)
