# 21 — Testing DAGs: Cheatsheet

## Test Types Summary

| Test type | What it tests | Needs Airflow DB? | Speed |
|---|---|---|---|
| Import / DAGBag | DAG can be parsed and imported | No (just import) | Very fast |
| Structure | Task count, task IDs, dependencies, tags | No | Fast |
| Unit | Python callable logic | No | Very fast |
| Integration | Hooks + operators with mocked connections | No (mocked) | Fast |
| End-to-end | Full DAG run against test environment | Yes | Slow |

---

## conftest.py Setup

```python
# tests/conftest.py
import os
import pytest
from airflow.models import DagBag

# Tell Airflow not to try connecting to a real DB when importing DAGs
os.environ["AIRFLOW__CORE__UNIT_TEST_MODE"] = "True"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = "sqlite:////tmp/test_airflow.db"

@pytest.fixture(scope="session")
def dagbag():
    """Load all DAGs once per test session."""
    return DagBag(dag_folder="dags/", include_examples=False)

@pytest.fixture
def get_dag(dagbag):
    """Helper fixture to retrieve a specific DAG by ID."""
    def _get(dag_id: str):
        dag = dagbag.get_dag(dag_id)
        assert dag is not None, f"DAG '{dag_id}' not found in DagBag"
        return dag
    return _get
```

---

## Common Test Patterns

### Import test
```python
def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}, f"Errors: {dagbag.import_errors}"
```

### Task count test
```python
def test_task_count(get_dag):
    dag = get_dag("my_etl")
    assert len(dag.tasks) == 5
```

### Task IDs test
```python
def test_required_tasks_exist(get_dag):
    dag = get_dag("my_etl")
    task_ids = {t.task_id for t in dag.tasks}
    assert {"extract", "transform", "load"}.issubset(task_ids)
```

### Dependency test
```python
def test_task_order(get_dag):
    dag = get_dag("my_etl")
    extract   = dag.get_task("extract")
    transform = dag.get_task("transform")
    assert transform.task_id in [t.task_id for t in extract.downstream_list]
```

### Tags and description
```python
def test_all_dags_have_tags(dagbag):
    for dag_id, dag in dagbag.dags.items():
        assert dag.tags, f"'{dag_id}' has no tags"
```

---

## Mock Patterns for Hooks

```python
from unittest.mock import patch, MagicMock

# Mock PostgresHook
with patch("dags.my_dag.PostgresHook") as MockHook:
    MockHook.return_value.get_records.return_value = [(1, "Alice")]
    # ... call function that uses PostgresHook

# Mock S3Hook
with patch("dags.my_dag.S3Hook") as MockS3:
    MockS3.return_value.check_for_key.return_value = True
    MockS3.return_value.read_key.return_value = "csv,data,here"
    # ... call function that uses S3Hook

# Mock using pytest-mock (cleaner)
def test_with_mocker(mocker):
    mock_hook = mocker.patch("dags.my_dag.PostgresHook")
    mock_hook.return_value.get_records.return_value = []
    # ...
```

---

## CI/CD Checklist

- [ ] `test_no_import_errors` — catches any unparseable DAG
- [ ] `test_all_dags_have_tags` — enforces documentation conventions
- [ ] Structure tests for each production DAG
- [ ] Unit tests for all complex callable logic
- [ ] Mock all external hooks and connections
- [ ] Set `AIRFLOW__CORE__UNIT_TEST_MODE=True` in CI environment
- [ ] Run `pytest tests/ -v --tb=short` in GitHub Actions on push and PR
- [ ] Fail the CI build if any test fails (block the merge)

---

## Environment Variables for Testing

```bash
AIRFLOW__CORE__UNIT_TEST_MODE=True
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/test_airflow.db
AIRFLOW__CORE__DAGS_FOLDER=./dags
```

---

## Navigation

**Prev:** [20 — Monitoring and Alerting](../20_Monitoring_and_Alerting/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [22 — Custom Timetables](../22_Custom_Timetables/Cheatsheet.md)
