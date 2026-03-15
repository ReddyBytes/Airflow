# 25 — Secrets and Security: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Secrets Backend Configuration

| Backend | pip Package | `backend` Class |
|---|---|---|
| HashiCorp Vault | `apache-airflow-providers-hashicorp` | `airflow.providers.hashicorp.secrets.vault.VaultBackend` |
| AWS Secrets Manager | `apache-airflow-providers-amazon` | `airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend` |
| GCP Secret Manager | `apache-airflow-providers-google` | `airflow.providers.google.cloud.secrets.secret_manager.CloudSecretManagerBackend` |
| Azure Key Vault | `apache-airflow-providers-microsoft-azure` | `airflow.providers.microsoft.azure.secrets.key_vault.AzureKeyVaultBackend` |
| Local Filesystem | `apache-airflow` (built-in) | `airflow.secrets.local_filesystem.LocalFilesystemBackend` |

### airflow.cfg Secrets Section Template
```ini
[secrets]
backend = <backend_class>
backend_kwargs = {"connections_prefix": "airflow/connections", "variables_prefix": "airflow/variables"}
```

---

## Backend-Specific kwargs

### HashiCorp Vault
```json
{
    "url": "https://vault.corp.com:8200",
    "auth_type": "approle",
    "role_id": "airflow-role-id",
    "secret_id": "airflow-secret-id",
    "mount_point": "secret",
    "connections_path": "airflow/connections",
    "variables_path": "airflow/variables",
    "config_path": "airflow/config"
}
```

### AWS Secrets Manager
```json
{
    "connections_prefix": "airflow/connections",
    "variables_prefix": "airflow/variables",
    "region_name": "us-east-1",
    "profile_name": null
}
```

### GCP Secret Manager
```json
{
    "connections_prefix": "airflow-connections",
    "variables_prefix": "airflow-variables",
    "project_id": "my-gcp-project",
    "gcp_keyfile_dict": null
}
```

---

## Secret Path Conventions

| Secret Type | Vault Path | AWS Path | GCP Name |
|---|---|---|---|
| Connection `postgres_warehouse` | `secret/airflow/connections/postgres_warehouse` | `airflow/connections/postgres_warehouse` | `airflow-connections-postgres-warehouse` |
| Variable `api_key` | `secret/airflow/variables/api_key` | `airflow/variables/api_key` | `airflow-variables-api-key` |

---

## Environment Variable Secret Format

```bash
# Connection (URI format)
export AIRFLOW_CONN_{CONN_ID_UPPERCASE}="conn_type://login:password@host:port/schema"

# Examples:
export AIRFLOW_CONN_POSTGRES_PROD="postgresql://user:p%40ss@host:5432/mydb"
export AIRFLOW_CONN_S3_DEFAULT="s3://@"
export AIRFLOW_CONN_SLACK_DEFAULT="http://:xoxb-token@slack.com"

# Variable
export AIRFLOW_VAR_{VAR_NAME_UPPERCASE}="value"
export AIRFLOW_VAR_API_KEY="sk_prod_abc123"
export AIRFLOW_VAR_ENVIRONMENT="production"
```

URL-encode special chars in passwords: `@`→`%40`, `#`→`%23`, `/`→`%2F`, `:`→`%3A`

---

## Fernet Key Setup

```bash
# 1. Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Set in airflow.cfg
# [core]
# fernet_key = <generated_key>

# 3. Or set via environment variable (preferred)
export AIRFLOW__CORE__FERNET_KEY="<generated_key>"
```

### Fernet Key Rotation
```bash
# Step 1: Add new key first, old key second (comma-separated)
export AIRFLOW__CORE__FERNET_KEY="NEW_KEY,OLD_KEY"

# Step 2: Re-encrypt all secrets with new key
airflow db migrate

# Step 3: Remove old key
export AIRFLOW__CORE__FERNET_KEY="NEW_KEY"
```

---

## RBAC Roles Permission Table

| Permission | Admin | Op | User | Viewer | Public |
|---|---|---|---|---|---|
| View DAGs | Yes | Yes | Yes | Yes | No |
| View task logs | Yes | Yes | Yes | Yes | No |
| Trigger DAG runs | Yes | Yes | Yes | No | No |
| Clear / retry tasks | Yes | Yes | No | No | No |
| Pause / unpause DAGs | Yes | Yes | No | No | No |
| Edit connections/variables | Yes | No | No | No | No |
| Manage users and roles | Yes | No | No | No | No |
| View audit logs | Yes | Yes | No | No | No |

### Create a Custom Role (CLI)
```bash
airflow roles create data_team
airflow roles add-perms data_team --resource DAGs --action can_read
airflow roles add-perms data_team --resource DAGs --action can_edit
```

---

## Auth Manager Config

```ini
# airflow.cfg
[core]
auth_manager = airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager

[api]
# JWT token expiry in seconds (default: 3600)
access_token_lifetime_minutes = 60
```

### JWT Token Workflow
```bash
# 1. Obtain token
TOKEN=$(curl -s -X POST "http://localhost:8080/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token')

# 2. Use token in API calls
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags"

# Token has form: header.payload.signature (standard JWT)
# Decode payload: echo "<payload>" | base64 -d | jq
```

---

## Security Checklist

- [ ] Fernet key generated and set (never use the default)
- [ ] Secrets backend configured (not storing secrets in metadata DB)
- [ ] `AIRFLOW_CONN_*` env vars used for local development (not real prod secrets)
- [ ] RBAC enabled (default in Airflow 3)
- [ ] Admin password changed from default
- [ ] API access restricted to JWT (not Basic auth in production)
- [ ] DAG `access_control` set for sensitive pipelines
- [ ] Vault/AWS IAM policy scoped to `airflow/*` prefix only
- [ ] SSL enabled on metadata DB connection
- [ ] Fernet key stored in secret manager (not plain text in config file)
