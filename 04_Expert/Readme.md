<div align="center">
⬅️ [Advanced Track](../03_Advanced/Readme.md) &nbsp;|&nbsp; 🏠 [Home](../00_Learning_Guide/Readme.md) &nbsp;|&nbsp; [Airflow 3 Features ➡️](../05_Airflow_3_Features/Readme.md)
</div>

---

# 🟣 Expert Track

> *You're building pipelines other people depend on. Now you need to extend Airflow itself — custom operators, plugin architecture, secrets management, and performance at scale.*

**[Start Here → Plugins and Customization (Theory.md)](23_Plugins_and_Customization/Theory.md)**

---

## At a Glance

| | |
|---|---|
| **Topics** | 7 modules |
| **Est. Time** | 15–20 hours |
| **Prerequisites** | 🔴 Advanced Track complete |
| **Unlocks** | ⚡ Airflow 3 Features |

---

## Section Map

```mermaid
mindmap
  root((🟣 Expert))
    Plugins & Customization
      Plugin manager
      Custom views
      Blueprints
      Menu links
    Custom Operators & Hooks
      BaseOperator subclass
      BaseHook subclass
      execute() method
      packaging operators
    Secrets & Security
      Secrets backends
      HashiCorp Vault
      AWS Secrets Manager
      GCP Secret Manager
      RBAC
    REST API
      Airflow REST API v2
      Triggering DAGs via API
      CI/CD integration
      Authentication
    Performance Tuning
      scheduler tuning
      parallelism settings
      DAG parsing optimization
      DB connection pools
    Remote Logging
      S3 log storage
      GCS log storage
      Elasticsearch
      log config
    DAG Patterns
      Factory pattern
      Config-driven DAGs
      Modular DAGs
      Reusable task groups
```

---

## Topics

| Module | File | Description |
|--------|------|-------------|
| 23 | [Plugins → Theory.md](23_Plugins_and_Customization/Theory.md) | Airflow plugin system, custom views, hooks |
| 23 | [Plugins → Cheatsheet](23_Plugins_and_Customization/Cheatsheet.md) | Plugin structure quick reference |
| 23 | [Plugins → Interview Q&A](23_Plugins_and_Customization/Interview_QA.md) | Plugin system interview questions |
| 24 | Custom Operators & Hooks → Theory.md | Building reusable operators from scratch |
| 24 | Custom Operators → Code Example | Full custom operator and hook implementation |
| 25 | Secrets & Security → Theory.md | Secrets backends, RBAC, audit logging |
| 25 | Secrets → Code Example | Vault and AWS Secrets Manager integration |
| 26 | REST API → Theory.md | Airflow REST API v2, triggering DAGs externally |
| 26 | REST API → Code Example | API calls from Python and curl |
| 27 | Performance Tuning → Theory.md | Scheduler config, DB tuning, parsing speed |
| 28 | Remote Logging → Theory.md | S3/GCS/Elasticsearch log backends |
| 28 | Remote Logging → Code Example | Logging config examples |
| 29 | DAG Patterns → Theory.md | Factory patterns, config-driven DAGs |
| 29 | DAG Patterns → Code Example | Production-ready DAG templates |

---

## Learning Path

```mermaid
flowchart LR
    A[23 Plugins] --> B[24 Custom Ops & Hooks]
    B --> C[25 Secrets & Security]
    C --> D[26 REST API]
    D --> E[27 Performance]
    E --> F[28 Remote Logging]
    F --> G[29 DAG Patterns]
    G --> H[⚡ Airflow 3 Features]
```

---

## Before You Start

- Advanced Track complete, especially Testing and Pools
- Familiarity with Python packaging (`setup.py` / `pyproject.toml`) helps for custom operators
- For the Secrets module: access to either HashiCorp Vault (local via Docker), AWS, or GCP

---

<div align="center">
⬅️ [Advanced Track](../03_Advanced/Readme.md) &nbsp;|&nbsp; 🏠 [Home](../00_Learning_Guide/Readme.md) &nbsp;|&nbsp; [Airflow 3 Features ➡️](../05_Airflow_3_Features/Readme.md)
</div>
