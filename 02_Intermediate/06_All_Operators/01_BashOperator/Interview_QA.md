# BashOperator — Interview Q&A

Your pipeline needs to call a shell script, compress a file, or invoke a CLI tool. Before the interview, make sure you can explain *how* BashOperator does that, *what can go wrong*, and *when to reach for something else* instead.

---

## Beginner Questions

**Q1. What is BashOperator and what problem does it solve?**

BashOperator lets you run any shell command or bash script from inside an Airflow DAG task. It solves the problem of integrating existing shell scripts and CLI tools into your pipeline without rewriting them in Python. You pass a command string, Airflow executes it in a subprocess, and the task succeeds or fails based on the exit code.

```python
from airflow.operators.bash import BashOperator

compress_files = BashOperator(
    task_id="compress_output",
    bash_command="gzip /data/output/daily_{{ ds }}.csv",
)
```

---

**Q2. What does the `bash_command` parameter do? Is it required?**

`bash_command` is the only required parameter (aside from `task_id`). It holds the command string that gets written to a temporary bash script and executed in a subprocess. It accepts:
- A single inline command: `"echo hello"`
- A multi-line string with `"""..."""`
- A path to an existing `.sh` file (add a trailing space to avoid Jinja treating the filename as a template)

---

**Q3. What does exit code 0 mean? What happens with a non-zero exit code?**

Exit code `0` is the universal Unix signal for "success". Any other code means something went wrong. BashOperator checks the exit code after the subprocess finishes:

- **Exit code 0** → task marked as **success**
- **Non-zero exit code** → Airflow raises `AirflowException`, task is marked as **failed**

This is exactly how your terminal works — if a command fails, it returns a non-zero code. BashOperator respects that contract.

---

**Q4. How do you pass environment variables to a BashOperator task?**

Use the `env` parameter, which accepts a dictionary of key-value pairs. These become environment variables available inside the subprocess:

```python
BashOperator(
    task_id="run_script",
    bash_command="python /scripts/extract.py",
    env={
        "DB_HOST": "postgres.internal",
        "RUN_DATE": "{{ ds }}",   # Jinja templates work here
    },
)
```

Inside your script: `import os; date = os.environ["RUN_DATE"]`

By default (`append_env=True`), these are *merged* with the current system environment. Set `append_env=False` to pass *only* the vars you specify.

---

**Q5. Where is BashOperator imported from in Airflow 3?**

```python
from airflow.operators.bash import BashOperator
```

It is part of the Airflow core — no extra provider package needed.

---

## Intermediate Questions

**Q6. How does BashOperator return a value to downstream tasks?**

BashOperator automatically captures stdout from the subprocess and pushes the **last line of stdout** to XCom under the key `return_value`. Downstream tasks can pull this value:

```python
count_rows = BashOperator(
    task_id="count_rows",
    bash_command="wc -l /data/output.csv | awk '{print $1}'",
)

def check(**context):
    count = context["ti"].xcom_pull(task_ids="count_rows")
    print(f"Row count: {count}")
```

Only the *last line* is captured — if your command prints multiple lines, structure it so the final line is the value you care about.

---

**Q7. What is `append_env` and when would you set it to `False`?**

`append_env=True` (the default) means the subprocess inherits all environment variables from the Airflow worker process, plus any you add in `env`. This is usually what you want.

`append_env=False` means the subprocess gets *only* the variables you define in `env`, with no inherited environment. Use this when:
- You want a clean, reproducible environment
- You need to prevent sensitive worker env vars from leaking into the subprocess
- You are debugging and want to isolate exactly what the script sees

---

**Q8. How do you run a multi-line bash script in BashOperator?**

Use a triple-quoted Python string. Airflow writes the entire block to a temporary file and runs it as a bash script:

```python
BashOperator(
    task_id="pipeline_steps",
    bash_command="""
        set -e                          # Exit immediately on any error
        mkdir -p /data/{{ ds }}
        python /scripts/download.py --date={{ ds }}
        python /scripts/transform.py --date={{ ds }}
        echo "All steps complete for {{ ds }}"
    """,
)
```

`set -e` is a best practice — without it, a failed command in the middle won't stop the script (only the final exit code matters).

---

**Q9. What happens when a bash command fails partway through a multi-line script?**

Without `set -e`, bash continues executing subsequent lines even after a failure. The overall exit code is the exit code of the *last command*. This can mask errors — early lines fail silently, the last line succeeds, and the Airflow task is marked success.

**Best practice:** always start multi-line bash scripts with `set -e` (exit on first error) or `set -eo pipefail` (also catches errors in pipes):

```bash
set -eo pipefail
cat /data/input.csv | python /scripts/process.py > /data/output.csv
```

---

**Q10. What is `skip_exit_code` and when is it useful?**

`skip_exit_code` lets you designate a specific non-zero exit code to mean "skip this task" rather than "fail this task". This is useful for optional or conditional processing:

```python
BashOperator(
    task_id="optional_cleanup",
    bash_command="""
        if [ ! -f /data/{{ ds }}/temp.csv ]; then
            exit 99   # No file found — skip, don't fail
        fi
        rm /data/{{ ds }}/temp.csv
    """,
    skip_exit_code=99,
)
```

When the subprocess exits with code 99, the task is marked as `skipped` rather than `failed`.

---

## Advanced Questions

**Q11. What are the security risks of using BashOperator with user-supplied input?**

BashOperator passes your command string directly to a shell — this makes it vulnerable to **shell injection** if any part of the command comes from untrusted input.

```python
# DANGEROUS — never do this
user_date = get_user_input()  # could be "2024-01-01; rm -rf /"
BashOperator(bash_command=f"python process.py --date={user_date}")
```

Mitigations:
- **Never interpolate untrusted strings into `bash_command`** — use `env` to pass values safely and read them inside the script with `$VAR`
- Use `PythonOperator` when you need to handle user input — Python gives you proper argument escaping
- Validate and sanitize all dynamic inputs before passing them to bash
- Run tasks with a dedicated low-privilege system user

---

**Q12. When should you use BashOperator vs PythonOperator?**

| Situation | Use |
|---|---|
| Calling an existing shell script | BashOperator |
| Using CLI tools (aws cli, dbt, curl) | BashOperator |
| Quick file operations (copy, compress, move) | BashOperator |
| Complex business logic | PythonOperator |
| Calling Python libraries (pandas, requests) | PythonOperator |
| Structured error handling needed | PythonOperator |
| Reading Airflow connections securely | PythonOperator |
| User-supplied dynamic input | PythonOperator |

The rule of thumb: if you would type it in your terminal, BashOperator is fine. If you would write it as a Python module, use PythonOperator.

---

**Q13. How do you handle large stdout output from a BashOperator task?**

BashOperator captures the last line of stdout for XCom. If your command prints thousands of lines, all of it goes to the task log — this can bloat logs and slow down the UI.

Strategies:
- **Redirect verbose output to a file**: `python heavy_script.py > /tmp/output.log 2>&1 && echo "done"`
- **Only print the summary line last** — XCom only captures the final line
- **Use `output_encoding`** to handle non-UTF-8 output from legacy tools
- For large structured data, write to a file or database and pass the file path via XCom instead of the data itself

---

**Q14. Which parameters in BashOperator support Jinja templating?**

The `template_fields` of BashOperator are: `bash_command`, `env`, `cwd`. This means you can use `{{ ds }}`, `{{ execution_date }}`, `{{ var.value.my_var }}`, and other Jinja expressions inside all three parameters.

```python
BashOperator(
    task_id="dated_task",
    bash_command="python process.py --date={{ ds }} --run={{ run_id }}",
    cwd="/data/{{ macros.ds_format(ds, '%Y-%m-%d', '%Y/%m') }}",
    env={"MONTH": "{{ macros.ds_format(ds, '%Y-%m-%d', '%Y-%m') }}"},
)
```

Templates are rendered at runtime, just before the task executes.

---

**Q15. What is the `cwd` parameter and why does it matter?**

`cwd` sets the working directory for the subprocess. If not set, the subprocess starts from Airflow's home directory, which can cause relative path references to fail:

```python
BashOperator(
    task_id="run_local_script",
    bash_command="python process.py",   # process.py must be in cwd
    cwd="/opt/airflow/scripts",
)
```

This is especially important when running scripts that use relative imports, relative file paths, or config files expected to be in the current directory.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [../../06_All_Operators/Theory.md](../Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [02_PythonOperator](../02_PythonOperator/Theory.md)
