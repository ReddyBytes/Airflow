# 21 — Testing DAGs: Interview Q&A

---

**Q1. How do you test Airflow DAGs?**

Testing Airflow DAGs involves four layers. First, import tests using `DagBag` — these verify every DAG file can be parsed without errors. Second, structure tests — these verify task count, task IDs, dependencies, tags, and descriptions. Third, unit tests — test Python callable functions in isolation, no Airflow or database needed. Fourth, integration tests — test operators with mocked hooks to verify that tasks call the right connections with the right arguments. Run all of these with pytest in CI on every code push.

---

**Q2. What is a DAGBag test and why is it the most important test?**

A `DagBag` test loads all your DAG files using the same parser that the Airflow scheduler uses. If any DAG has a syntax error, an import error, a circular dependency, or a misconfigured parameter, it shows up in `dagbag.import_errors`. This is the most important test because a DAG with an import error simply doesn't appear in the Airflow UI — it fails silently. The test catches these failures in CI before they ever reach the scheduler:

```python
def test_no_import_errors():
    from airflow.models import DagBag
    dagbag = DagBag(dag_folder="dags/", include_examples=False)
    assert dagbag.import_errors == {}
```

---

**Q3. How do you mock Airflow connections (PostgresHook, S3Hook) in tests?**

Use `unittest.mock.patch` to replace the hook class with a mock before the function under test imports or instantiates it:

```python
from unittest.mock import patch

def test_extract():
    with patch("dags.my_dag.PostgresHook") as MockHook:
        MockHook.return_value.get_records.return_value = [(1, "Alice")]
        from dags.my_dag import extract
        result = extract()
    assert len(result) == 1
```

Never connect to real databases or cloud services in unit tests — it makes tests slow, flaky, and environment-dependent.

---

**Q4. What should you test in a DAG beyond "does it import"?**

Structure: does the DAG have the right number of tasks? Are the expected task IDs present? Are the dependencies correct (A runs before B)? Do all DAGs have tags and descriptions (team conventions)? Logic: do the Python callable functions transform data correctly? Do they handle edge cases (empty input, null values, type coercion)? Behavior: when a hook is mocked to return specific data, does the task process it correctly and return the right XCom value?

---

**Q5. How do you set up pytest for Airflow testing?**

Create a `tests/conftest.py` that sets the required environment variables before any Airflow imports:

```python
import os
os.environ["AIRFLOW__CORE__UNIT_TEST_MODE"] = "True"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = "sqlite:////tmp/test.db"
```

Then create a `dagbag` fixture that loads all DAGs once per session. Install `pytest` and `apache-airflow` in your test environment. Run with `pytest tests/ -v`.

---

**Q6. Why is AIRFLOW__CORE__UNIT_TEST_MODE important in CI?**

Setting `UNIT_TEST_MODE=True` tells Airflow not to attempt connections to a real metadata database during DAG imports and tests. Without this, Airflow might try to connect to a PostgreSQL or MySQL database that doesn't exist in your CI environment, causing import errors that have nothing to do with your DAG code. In unit test mode, Airflow uses in-memory state or a lightweight SQLite database, making tests fast and portable.

---

**Q7. How do you test that task A runs before task B?**

Use the `downstream_list` and `upstream_list` properties on task objects:

```python
def test_extract_before_transform(get_dag):
    dag = get_dag("my_etl")
    extract   = dag.get_task("extract")
    transform = dag.get_task("transform")
    downstream_ids = [t.task_id for t in extract.downstream_list]
    assert "transform" in downstream_ids
```

---

**Q8. How do you integrate DAG tests into a CI/CD pipeline?**

Create a GitHub Actions workflow (or equivalent) that: checks out the code, installs Python and dependencies, sets the test environment variables, and runs `pytest tests/ -v --tb=short`. Configure it to trigger on push and pull request events, and make the CI check required before merging. A minimal GitHub Actions workflow:

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install apache-airflow pytest pytest-mock
      - run: pytest tests/ -v
        env:
          AIRFLOW__CORE__UNIT_TEST_MODE: "True"
          AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: "sqlite:////tmp/test.db"
```

---

## Navigation

**Prev:** [20 — Monitoring and Alerting](../20_Monitoring_and_Alerting/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [22 — Custom Timetables](../22_Custom_Timetables/Interview_QA.md)
