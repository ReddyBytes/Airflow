# 21 — Testing DAGs

## The Story

You pushed a DAG with a typo in the schedule expression. It failed silently for 3 days.

The scheduler tried to parse the DAG, hit the syntax error, logged a warning, and moved on. The DAG never appeared in the UI. No alert fired because the DAG didn't exist yet as far as Airflow was concerned. Three days later someone asked "where are the reports?" and the investigation led back to a single typo on line 8.

A simple import test would have caught this in the CI pipeline in 2 seconds.

**Testing your DAGs before deployment catches bugs before they reach production.** Not just typos — import errors, missing connections, wrong task counts, broken callable logic, misconfigured dependencies. A test suite that runs in CI gives you confidence that every push is deployable.

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Types of Tests](#types-of-tests) · [DAGBag Loading Test](#dagbag-loading-test) · [Mocking External Connections](#mocking-external-connections)

**Should Learn** — important for real projects and interviews:
[Unit Testing PythonOperator Callables](#unit-testing-pythonoperator-callables) · [CI/CD Integration](#cicd-integration-github-actions)

**Good to Know** — useful in specific situations, not needed daily:
[pytest Setup for Airflow](#pytest-setup-for-airflow)

**Reference** — skim once, look up when needed:
[Key Takeaways](#key-takeaways)

---

## Types of Tests

### 1. Import Test (DAGBag Test)
The fastest and most important test. Verifies that every DAG file can be imported without syntax errors or missing dependencies.

```python
from airflow.models import DagBag

def test_dag_import():
    dagbag = DagBag(dag_folder="./dags", include_examples=False)
    assert len(dagbag.import_errors) == 0, f"Import errors: {dagbag.import_errors}"
```

If this fails, the DAG won't appear in the Airflow UI at all.

### 2. Structure Test
Verifies that a DAG has the expected structure: correct task count, expected task IDs, correct dependencies, required tags and documentation.

```python
def test_dag_has_expected_tasks():
    dagbag = DagBag(dag_folder="./dags", include_examples=False)
    dag = dagbag.get_dag("my_etl_pipeline")
    assert dag is not None
    assert len(dag.tasks) == 5
    task_ids = [t.task_id for t in dag.tasks]
    assert "extract" in task_ids
    assert "load" in task_ids
```

### 3. Unit Test
Tests individual Python callables (the functions used inside `PythonOperator` tasks) in isolation — no Airflow, no database, just the function logic.

```python
def test_transform_function():
    from dags.my_dag import transform_data
    result = transform_data({"name": " Alice ", "age": "30"})
    assert result["name"] == "Alice"   # stripped
    assert result["age"] == 30         # cast to int
```

### 4. Integration Test
Tests that tasks interact correctly with external systems using mocked connections. Verifies the full task execution path without needing a live database or S3 bucket.

```python
from unittest.mock import patch

def test_extract_task_queries_db():
    with patch("dags.my_dag.PostgresHook") as mock_hook:
        mock_hook.return_value.get_records.return_value = [(1, "Alice"), (2, "Bob")]
        from dags.my_dag import extract
        result = extract()
        assert len(result) == 2
```

---

## pytest Setup for Airflow

Install test dependencies:
```bash
pip install pytest apache-airflow pytest-mock
```

Recommended project structure:
```
dags/
    my_etl_pipeline.py
    utils/
        transformations.py
tests/
    conftest.py
    test_dag_integrity.py
    test_transformations.py
```

---

## DAGBag Loading Test

`DagBag` is Airflow's DAG collection class. Loading a `DagBag` triggers the same parsing that the scheduler performs. Any syntax error, import error, or cycle in task dependencies will show up as an import error.

```python
from airflow.models import DagBag

def test_no_import_errors():
    """Catch any DAG that can't be parsed."""
    dagbag = DagBag(dag_folder="dags/", include_examples=False)
    assert dagbag.import_errors == {}, \
        f"DAG import errors found:\n{dagbag.import_errors}"

def test_all_dags_have_tags():
    """Enforce that every DAG has at least one tag for organization."""
    dagbag = DagBag(dag_folder="dags/", include_examples=False)
    for dag_id, dag in dagbag.dags.items():
        assert dag.tags, f"DAG '{dag_id}' has no tags"

def test_all_dags_have_descriptions():
    """Enforce that every DAG has a description."""
    dagbag = DagBag(dag_folder="dags/", include_examples=False)
    for dag_id, dag in dagbag.dags.items():
        assert dag.description, f"DAG '{dag_id}' has no description"
```

---

## Unit Testing PythonOperator Callables

Test the Python functions independently — no need to spin up Airflow at all.

```python
# dags/transformations.py
def normalize_customer_record(record: dict) -> dict:
    return {
        "id":    record["id"],
        "name":  record["name"].strip().title(),
        "email": record["email"].lower(),
        "age":   int(record["age"]),
    }

# tests/test_transformations.py
from dags.transformations import normalize_customer_record

def test_name_is_stripped_and_titled():
    result = normalize_customer_record(
        {"id": 1, "name": " alice smith ", "email": "Alice@Example.COM", "age": "28"}
    )
    assert result["name"] == "Alice Smith"

def test_email_is_lowercased():
    result = normalize_customer_record(
        {"id": 1, "name": "Bob", "email": "BOB@EXAMPLE.COM", "age": "35"}
    )
    assert result["email"] == "bob@example.com"

def test_age_is_cast_to_int():
    result = normalize_customer_record(
        {"id": 1, "name": "Carol", "email": "c@x.com", "age": "42"}
    )
    assert isinstance(result["age"], int)
    assert result["age"] == 42

def test_invalid_age_raises():
    import pytest
    with pytest.raises(ValueError):
        normalize_customer_record(
            {"id": 1, "name": "Dave", "email": "d@x.com", "age": "not-a-number"}
        )
```

---

## Mocking External Connections

Never connect to real databases, S3 buckets, or APIs in unit tests. Use `unittest.mock` to replace hooks with controlled fakes.

```python
from unittest.mock import MagicMock, patch

def test_extract_task_with_mocked_postgres():
    """Test that extract() calls PostgresHook and returns formatted records."""
    mock_records = [(1, "Alice", "alice@example.com"), (2, "Bob", "bob@example.com")]

    with patch("dags.my_etl.PostgresHook") as MockHook:
        instance = MockHook.return_value
        instance.get_records.return_value = mock_records

        from dags.my_etl import extract_customers
        result = extract_customers(postgres_conn_id="postgres_default")

        # Verify the hook was called with the right connection
        MockHook.assert_called_once_with(postgres_conn_id="postgres_default")
        # Verify the result was formatted correctly
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
```

---

## CI/CD Integration: GitHub Actions

A GitHub Actions workflow that runs the test suite on every push and pull request:

```yaml
# .github/workflows/airflow_tests.yml
name: Airflow DAG Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install apache-airflow pytest pytest-mock
      - name: Run tests
        env:
          AIRFLOW__CORE__UNIT_TEST_MODE: "True"
          AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: "sqlite:////tmp/airflow_test.db"
        run: pytest tests/ -v --tb=short
```

---

## Key Takeaways

- The DAGBag import test is the most important test — it catches any DAG that won't load.
- Unit test your Python callables independently; they don't need Airflow to run.
- Mock all external connections (`PostgresHook`, `S3Hook`, etc.) — never connect to real systems in tests.
- Structure tests enforce team conventions (tags, descriptions, task count, dependency order).
- Run tests in CI on every push — catch issues before they reach the scheduler.
- Set `AIRFLOW__CORE__UNIT_TEST_MODE=True` in CI to prevent Airflow from trying to connect to a real database during import.

---

## Navigation

**Prev:** [20 — Monitoring and Alerting](../20_Monitoring_and_Alerting/Theory.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [22 — Custom Timetables](../22_Custom_Timetables/Theory.md)
