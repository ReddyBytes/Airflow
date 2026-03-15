# 07 — Connections and Hooks: Cheatsheet

## Connection Types Quick Reference

| conn_type | Provider Package | Typical Use |
|---|---|---|
| `postgres` | `apache-airflow-providers-postgres` | PostgreSQL databases |
| `mysql` | `apache-airflow-providers-mysql` | MySQL / MariaDB |
| `sqlite` | core | Local SQLite files |
| `http` | `apache-airflow-providers-http` | REST APIs |
| `aws` | `apache-airflow-providers-amazon` | S3, Redshift, RDS, etc. |
| `google_cloud_platform` | `apache-airflow-providers-google` | GCS, BigQuery, Pub/Sub |
| `azure_blob` | `apache-airflow-providers-microsoft-azure` | Azure Blob Storage |
| `snowflake` | `apache-airflow-providers-snowflake` | Snowflake DWH |
| `kafka` | `apache-airflow-providers-apache-kafka` | Kafka topics |
| `ssh` | `apache-airflow-providers-ssh` | SSH / SFTP |

---

## Three Ways to Set a Connection

### 1. Airflow UI
Admin → Connections → + → fill fields → Save

### 2. Environment Variable (URI format)
```bash
# Pattern
export AIRFLOW_CONN_<CONN_ID_UPPERCASE>=<scheme>://<login>:<password>@<host>:<port>/<schema>

# Postgres example
export AIRFLOW_CONN_MY_POSTGRES=postgresql://user:pass@localhost:5432/mydb

# HTTP example
export AIRFLOW_CONN_MY_API=http://https%3A%2F%2Fapi.example.com

# AWS example (extra fields go in the query string as JSON)
export AIRFLOW_CONN_MY_AWS=aws://AKIAIOSFODNN7EXAMPLE:wJalrXU@/?region_name=us-east-1
```

### 3. Secrets Backend (production)
Configure in `airflow.cfg`:
```ini
[secrets]
backend = airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend
backend_kwargs = {"connections_prefix": "airflow/connections", "region_name": "us-east-1"}
```

---

## Common Connection Parameters

| Parameter | Field in UI | Notes |
|---|---|---|
| `conn_id` | Connection Id | Snake_case, unique across Airflow |
| `conn_type` | Connection Type | Controls which fields are shown |
| `host` | Host | Hostname, IP, or URL |
| `schema` | Schema | Database name for DBs |
| `login` | Login | Username or access key ID |
| `password` | Password | Stored encrypted in metadata DB |
| `port` | Port | Numeric port |
| `extra` | Extra | JSON string for additional config |

---

## Hook vs Operator

| | Hook | Operator |
|---|---|---|
| **Abstraction level** | Low | High |
| **When to use** | You need custom logic | Standard operation |
| **Returns data** | Yes — you handle it | Task result only |
| **Example** | `PostgresHook.get_records()` | `PostgresOperator` |
| **Location in task** | Inside `PythonOperator` | Is the task itself |

---

## Instantiating Common Hooks

```python
# Postgres
from airflow.providers.postgres.hooks.postgres import PostgresHook
hook = PostgresHook(postgres_conn_id="my_postgres")

# S3
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
hook = S3Hook(aws_conn_id="my_aws")

# HTTP
from airflow.providers.http.hooks.http import HttpHook
hook = HttpHook(method="GET", http_conn_id="my_api")

# Get raw Connection object (works for any type)
from airflow.hooks.base import BaseHook
conn = BaseHook.get_connection("my_conn_id")
print(conn.host, conn.login, conn.password)
```

---

## Environment Variable URI Format

```
<conn_type>://<login>:<password>@<host>:<port>/<schema>?<extra_as_query_string>
```

Special characters in login/password must be URL-encoded (`@` → `%40`, `/` → `%2F`).
