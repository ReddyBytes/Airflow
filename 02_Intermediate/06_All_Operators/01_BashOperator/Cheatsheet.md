# BashOperator — Cheatsheet

Your go-to reference card for BashOperator. Keep this open during code review, interviews, and whenever you need a quick reminder on parameters or patterns.

---

## What It Does in One Sentence

Runs any shell command or bash script as an Airflow task — success if exit code is 0, failure otherwise.

---

## Import

```python
from airflow.operators.bash import BashOperator
```

No provider package needed — part of Airflow core.

---

## Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `bash_command` | `str` | **required** | Shell command, multi-line script, or path to `.sh` file |
| `env` | `dict` | `None` | Environment variables to inject into the subprocess |
| `append_env` | `bool` | `True` | `True` = merge with system env; `False` = only vars in `env` |
| `output_encoding` | `str` | `'utf-8'` | Encoding used to decode stdout |
| `skip_exit_code` | `int` | `None` | Exit code that triggers task **skip** instead of **failure** |
| `cwd` | `str` | `None` | Working directory for the subprocess |

---

## Template Fields (Jinja-aware)

`bash_command`, `env`, `cwd` — all three support `{{ ds }}`, `{{ run_id }}`, `{{ var.value.x }}`, etc.

---

## Code Patterns

### Single Command

```python
BashOperator(
    task_id="check_disk",
    bash_command="df -h /",
)
```

---

### Multi-line Script

```python
BashOperator(
    task_id="process_files",
    bash_command="""
        set -eo pipefail
        mkdir -p /data/{{ ds }}
        python /scripts/transform.py --date={{ ds }}
        echo "transform complete"
    """,
)
```

Always use `set -eo pipefail` at the top — without it, early failures are silently ignored.

---

### With Environment Variables

```python
BashOperator(
    task_id="run_with_env",
    bash_command="python /scripts/load.py",
    env={
        "DB_HOST": "postgres.internal",
        "RUN_DATE": "{{ ds }}",
        "BATCH_SIZE": "500",
    },
    append_env=True,   # inherit system env + add yours
)
```

---

### With Jinja Templating

```python
BashOperator(
    task_id="dated_archive",
    bash_command="tar -czf /archive/{{ ds_nodash }}.tar.gz /data/{{ ds }}/",
    cwd="/opt/airflow",
)
```

---

### Capturing Output via XCom

```python
# XCom gets the LAST line of stdout automatically
count_rows = BashOperator(
    task_id="count_rows",
    bash_command="wc -l /data/{{ ds }}/output.csv | awk '{print $1}'",
)

# Pull in downstream task
count = context["ti"].xcom_pull(task_ids="count_rows")
```

---

### Skip on Condition

```python
BashOperator(
    task_id="optional_step",
    bash_command="""
        [ -f /data/{{ ds }}/flag.txt ] || exit 99
        python /scripts/optional.py --date={{ ds }}
    """,
    skip_exit_code=99,
)
```

---

### Running a Script File

```python
BashOperator(
    task_id="run_script",
    bash_command="/opt/airflow/scripts/cleanup.sh ",   # trailing space prevents Jinja treating filename as template
    cwd="/opt/airflow/scripts",
)
```

---

## When to Use BashOperator

| Use it when... | Avoid it when... |
|---|---|
| Wrapping an existing shell script | Logic requires Python libraries (use PythonOperator) |
| Using CLI tools (dbt run, aws s3 cp, curl) | Handling user-supplied dynamic input (injection risk) |
| Quick file ops (copy, compress, move) | You need Airflow connections (use provider operators) |
| Running Python *scripts* not in your DAG | Complex structured error handling needed |
| Calling system commands (df, ping, cron) | You need to return structured data from the task |

---

## Common Pitfalls

1. **Forgetting `set -e`** — multi-line scripts continue after a failed command; add `set -eo pipefail` at the top
2. **Shell injection** — never interpolate untrusted strings into `bash_command`; use `env` instead
3. **Only last line in XCom** — if your command prints multiple lines, only the final one is captured
4. **Trailing space on script paths** — required to prevent Jinja from resolving the `.sh` filename as a template
5. **Relative paths fail without `cwd`** — always set `cwd` when your script uses relative file references

---

## Golden Rules

- Every multi-line script should start with `set -eo pipefail` — never silently swallow errors
- Pass dynamic values through `env`, not by interpolating them into `bash_command` — prevents injection
- XCom captures only the final stdout line — design your command output accordingly
- BashOperator is for wrapping shell tools, not replacing Python logic — complex tasks belong in PythonOperator
- Test your bash command in a terminal first — if it works there, BashOperator will run it the same way

---

## Quick Diagnosis

| Symptom | Likely Cause |
|---|---|
| Task succeeds but produces wrong result | `set -e` missing; an intermediate command failed silently |
| XCom value is wrong or empty | Command prints multiple lines; only last line is captured |
| `TemplateNotFound` error on `.sh` file | Missing trailing space after script path |
| Task fails with permission denied | Script not executable; run `chmod +x script.sh` |
| Environment variable not found in script | `append_env=False` was set; add the var to `env` dict |

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview prep |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [../../06_All_Operators/Theory.md](../Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [02_PythonOperator](../02_PythonOperator/Theory.md)
