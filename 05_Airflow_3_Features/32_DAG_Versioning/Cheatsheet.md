# DAG Versioning — Cheatsheet

## Navigation
⬅️ **Prev: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**

---

## How Versions Are Created

| Trigger | Creates New Version? |
|---------|---------------------|
| Task added | Yes |
| Task removed | Yes |
| Task renamed | Yes |
| Dependency order changed | Yes |
| Schedule/start_date changed | Yes |
| Task `bash_command` string changed | Implementation-dependent |
| Task `retries` changed | Implementation-dependent |
| File re-parsed with no structural change | No (hash match) |

Versions are computed via a structural hash of the DAG. If the hash matches the stored version, no new version is written.

---

## Version Assignment Rules

```
New DAG file deployed
        │
        ▼
DAG Processor parses file
        │
        ▼
Compute structural hash
        │
   Hash matches?──Yes──► No new version (current version stays active)
        │
        No
        ▼
Create new version (v_n+1)
        │
        ▼
New DagRuns use v_n+1
Old DagRuns retain v_n tag
```

---

## Configuration

```ini
# airflow.cfg

[dag_processor]
# Store DAG source code with each version (enables code diff view in UI)
store_dag_code = True

[scheduler]
# Max versions to retain per DAG before cleanup
max_dag_versions_to_store = 10
```

---

## UI Navigation for Versions

| Action | Location in UI |
|--------|----------------|
| Switch between DAG versions | DAG detail page → Version dropdown (top right) |
| See all versions | DAG detail page → Versions tab |
| See which version a run used | DagRun list → Version column |
| View run with its original structure | Click DagRun → Graph tab shows version-specific graph |
| Compare versions | Versions tab → select two versions → diff view |

---

## DagRun Version Association

```
DagRun created at time T  →  uses current DAG version at T
DagRun executes           →  always displays with version from creation time
DAG modified at time T+1  →  new DagRuns use new version
Old DagRun viewed at T+2  →  still shows version from T (not T+1 version)
```

---

## Best Practices Quick Reference

| Scenario | Recommendation |
|----------|---------------|
| Adding tasks | Safe — do it anytime |
| Removing tasks | Pause DAG first, let runs complete, then remove |
| Renaming tasks | Use new DAG ID for major refactors |
| Backfilling after restructure | Test carefully — task names must match |
| Major restructure | Create new DAG ID (e.g., `my_dag_v2`) |
| Version cleanup | Set `max_dag_versions_to_store = 10` in config |

---

## CLI Commands for Version Info

```bash
# List all DAG versions
airflow dags list-dag-versions --dag-id my_dag

# Show details of a specific version
airflow dags show --dag-id my_dag --version 3

# Show which version a DagRun used
airflow dags list-runs --dag-id my_dag --output table
# (version column shows in output)
```

---

## Navigation
⬅️ **Prev: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**
