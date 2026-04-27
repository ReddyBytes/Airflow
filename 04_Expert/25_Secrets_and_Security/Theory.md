# 25 — Secrets and Security

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Secrets Backend Lookup Chain](#1-how-secrets-backends-work) · [Fernet Key Encryption](#6-fernet-key-at-rest-encryption) · [Environment Variable Secrets](#5-environment-variable-secrets)

**Should Learn** — important for real projects and interviews:
[Vault Backend Config](#2-hashicorp-vault-backend) · [AWS Secrets Manager](#3-aws-secrets-manager-backend) · [RBAC Built-in Roles](#7-rbac-in-airflow-3)

**Good to Know** — useful in specific situations, not needed daily:
[GCP Secret Manager](#4-gcp-secret-manager-backend) · [Auth Manager and JWT](#8-auth-manager-in-airflow-3)

**Reference** — skim once, look up when needed:
[Vault Auth Types](#vault-auth-types) · [Fernet Key Rotation](#key-rotation)

---

## The Story

Your DAG files are in a public GitHub repo. You cannot hardcode database passwords. Storing them in Airflow's metadata database is possible — it supports Fernet encryption — but your security team controls a HashiCorp Vault cluster. They want every secret in Vault. Rotate a password in Vault, and the next DAG run picks it up automatically, no Airflow changes needed. Airflow's secrets backend system makes this possible.

---

## 1. How Secrets Backends Work

When Airflow resolves a Connection or Variable, it queries backends in order:

1. **Secrets Backend** (Vault, AWS Secrets Manager, etc.)
2. **Environment Variables** (`AIRFLOW_CONN_*`, `AIRFLOW_VAR_*`)
3. **Metadata Database** (connections and variables stored in Airflow)

The first backend that returns a value wins. If the secrets backend is configured and contains the secret, the metadata database is never consulted. This means:
- Secrets never touch the Airflow DB
- DAG code is unchanged — `Variable.get("db_password")` works regardless of backend
- Rotating a secret in Vault is immediately effective on the next DAG run

```mermaid
sequenceDiagram
    participant DAG as DAG / Operator
    participant AF as Airflow Core
    participant SB as Secrets Backend (Vault)
    participant ENV as Environment Vars
    participant DB as Metadata DB

    DAG->>AF: Variable.get("db_password")
    AF->>SB: query: airflow/variables/db_password
    alt found in Vault
        SB-->>AF: "s3cr3t_p@ssw0rd"
        AF-->>DAG: "s3cr3t_p@ssw0rd"
    else not in Vault
        SB-->>AF: not found
        AF->>ENV: AIRFLOW_VAR_DB_PASSWORD?
        alt found in env
            ENV-->>AF: value
            AF-->>DAG: value
        else not in env
            AF->>DB: SELECT value FROM variable WHERE key='db_password'
            DB-->>AF: encrypted value
            AF-->>DAG: decrypted value
        end
    end
```

---

## 2. HashiCorp Vault Backend

### Installation
```bash
pip install apache-airflow-providers-hashicorp
```

### airflow.cfg Configuration
```ini
[secrets]
backend = airflow.providers.hashicorp.secrets.vault.VaultBackend
backend_kwargs = {
    "connections_path": "airflow/connections",
    "variables_path": "airflow/variables",
    "config_path": "airflow/config",
    "url": "https://vault.corp.com:8200",
    "auth_type": "approle",
    "role_id": "airflow-role-id",
    "secret_id": "airflow-secret-id",
    "mount_point": "secret"
}
```

### Vault Secret Structure

For connections, Vault path: `secret/airflow/connections/postgres_warehouse`
```json
{
    "conn_type": "postgres",
    "host": "warehouse.corp.com",
    "login": "airflow_svc",
    "password": "p@ssw0rd_123",
    "port": 5432,
    "schema": "analytics"
}
```

For variables, Vault path: `secret/airflow/variables/api_key`
```json
{
    "value": "sk_prod_abc123xyz"
}
```

### Vault Auth Types

| Auth Type | `auth_type` Value | Use Case |
|---|---|---|
| Token | `"token"` | Development only |
| AppRole | `"approle"` | Service accounts |
| AWS IAM | `"aws_iam"` | EC2/ECS/EKS |
| Kubernetes | `"kubernetes"` | K8s pod service accounts |
| GCP | `"gcp"` | GCP workload identity |

---

## 3. AWS Secrets Manager Backend

### Installation
```bash
pip install apache-airflow-providers-amazon
```

### airflow.cfg Configuration
```ini
[secrets]
backend = airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend
backend_kwargs = {
    "connections_prefix": "airflow/connections",
    "variables_prefix": "airflow/variables",
    "profile_name": null,
    "region_name": "us-east-1"
}
```

### Secret Structure in AWS

Secret name: `airflow/connections/postgres_warehouse`
```json
{
    "conn_type": "postgresql",
    "host": "warehouse.us-east-1.rds.amazonaws.com",
    "login": "airflow_svc",
    "password": "p@ssw0rd_123",
    "port": 5432,
    "schema": "analytics"
}
```

For variables: `airflow/variables/api_key` (secret value is a plain string, not JSON).

### IAM Policy Required
```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "secretsmanager:GetSecretValue",
            "secretsmanager:ListSecrets"
        ],
        "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:airflow/*"
    }]
}
```

---

## 4. GCP Secret Manager Backend

### Installation
```bash
pip install apache-airflow-providers-google
```

### airflow.cfg Configuration
```ini
[secrets]
backend = airflow.providers.google.cloud.secrets.secret_manager.CloudSecretManagerBackend
backend_kwargs = {
    "connections_prefix": "airflow-connections",
    "variables_prefix": "airflow-variables",
    "gcp_keyfile_dict": null,
    "project_id": "my-gcp-project"
}
```

Secret name in GCP: `airflow-connections-postgres-warehouse` (hyphens, not underscores).

---

## 5. Environment Variable Secrets

No backend needed. Set before starting Airflow components:

```bash
# Connection: AIRFLOW_CONN_{CONN_ID_UPPERCASE}
# URI format: conn_type://login:password@host:port/schema?param=value
export AIRFLOW_CONN_POSTGRES_WAREHOUSE="postgresql://airflow_svc:p%40ssword@warehouse.corp.com:5432/analytics"

# Variable: AIRFLOW_VAR_{VAR_NAME_UPPERCASE}
export AIRFLOW_VAR_API_KEY="sk_prod_abc123xyz"
export AIRFLOW_VAR_MAX_RETRIES="3"
```

Note: URL-encode special characters in passwords (`@` → `%40`, `#` → `%23`).

---

## 6. Fernet Key (At-Rest Encryption)

Airflow encrypts connections and variables stored in the metadata database using Fernet symmetric encryption (AES 128 in CBC mode).

### Generate a Fernet Key
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Output example: mLJYtF4L35eS_6PxTqFTJaRVKxfD4vK8_5TqDpMoC5o=
```

### Configure in airflow.cfg
```ini
[core]
fernet_key = mLJYtF4L35eS_6PxTqFTJaRVKxfD4vK8_5TqDpMoC5o=
```

### Key Rotation
1. Generate new key
2. Add both keys (comma-separated — new first):
   ```ini
   fernet_key = NEW_KEY,OLD_KEY
   ```
3. Run `airflow db migrate` to re-encrypt all values with the new key
4. Remove old key after successful rotation

---

## 7. RBAC in Airflow 3

Airflow 3 ships with Flask-AppBuilder RBAC enabled by default.

### Built-in Roles

| Role | Description | Can Trigger DAGs? | Can Edit? | Can See All DAGs? |
|---|---|---|---|---|
| **Admin** | Full access, manage users and roles | Yes | Yes | Yes |
| **Op** | Operate: trigger, clear, set states | Yes | Config only | Yes |
| **User** | View and trigger DAGs | Yes | No | Yes (by default) |
| **Viewer** | Read-only | No | No | Yes |
| **Public** | Not authenticated | No | No | No |

### DAG-Level Access Control

In Airflow 3, DAGs can be restricted to specific roles:
```python
with DAG(
    dag_id="sensitive_pipeline",
    access_control={
        "data_team": {"can_read", "can_edit"},
        "viewers": {"can_read"},
    },
) as dag:
    ...
```

Role names in `access_control` correspond to roles created in the Airflow UI.

---

## 8. Auth Manager in Airflow 3

Airflow 3 introduces a pluggable **Auth Manager** that decouples authentication/authorization from the web framework. This replaces the hardcoded Flask-AppBuilder RBAC.

### Configuring the Auth Manager
```ini
[core]
auth_manager = airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager
```

Available Auth Managers:
- `FabAuthManager` — default, uses Flask-AppBuilder (local user database)
- AWS Auth Manager (via `apache-airflow-providers-amazon`)
- Custom implementations by inheriting `BaseAuthManager`

### API Authentication (JWT)

Airflow 3's API Server issues JWT tokens:

```bash
# Get a JWT token (Basic auth → JWT)
TOKEN=$(curl -s -X POST "http://localhost:8080/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token')

# Use the token
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/dags
```

Token expiry is configurable:
```ini
[api]
auth_backends = airflow.api.auth.backend.jwt_auth
jwt_secret_key = your-256-bit-secret
jwt_token_expiry = 3600   # seconds
```

---

## Key Takeaways

- Secrets backends are queried before the metadata DB — use them for any sensitive value
- The backend lookup chain: Vault/AWS/GCP → environment variables → metadata DB
- Fernet key is mandatory in production — generate one before your first deployment
- Rotate Fernet keys with two-key comma syntax; never just replace the key or existing secrets become undecryptable
- Airflow 3's Auth Manager is pluggable — AWS Auth Manager provides SSO integration without local user management
- JWT is the standard API authentication method in Airflow 3; Basic auth is available but not recommended for production
