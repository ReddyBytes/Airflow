# 03 — Step-by-Step Guide: Forex ETL Pipeline

Build the pipeline in 5 phases. Complete each phase, run the test command,
and confirm it succeeds before moving on.

---

## Phase 1 — Set Up Your Environment

Before writing any DAG code, get the infrastructure in place.

**1a. Start PostgreSQL:**
```bash
docker run -d \
  --name forex-postgres \
  -e POSTGRES_USER=airflow \
  -e POSTGRES_PASSWORD=airflow \
  -e POSTGRES_DB=forex \
  -p 5432:5432 \
  postgres:15
```

**1b. Create the currencies config file that the FileSensor will watch for:**
```bash
mkdir -p /tmp/forex
cat > /tmp/forex/currencies.json << 'EOF'
{
  "base": "USD",
  "currencies": ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY"]
}
EOF
```

**1c. Install the required providers:**
```bash
pip install apache-airflow-providers-http apache-airflow-providers-postgres
```

**1d. Create the Airflow connections:**
```bash
# HTTP connection pointing at the forex API base URL
airflow connections add 'forex_api' \
  --conn-type 'http' \
  --conn-host 'https://v6.exchangerate-api.com'

# Postgres connection pointing at the Docker container
airflow connections add 'forex_postgres' \
  --conn-type 'postgres' \
  --conn-host 'localhost' \
  --conn-login 'airflow' \
  --conn-password 'airflow' \
  --conn-schema 'forex' \
  --conn-port 5432
```

**Verify:** In the Airflow UI under Admin → Connections, click **Test** on each connection.

---

## Phase 2 — Build the Two Sensors

Sensors are guards. They wait for external conditions to be true before letting
the pipeline proceed. This DAG has two: "is the API alive?" and "does the config
file exist?"

Open `src/starter.py` and fill in the two sensor task definitions.

<details>
<summary>💡 Hint — HttpSensor parameters</summary>

The `HttpSensor` needs:
- `http_conn_id` — the connection ID you just created (`forex_api`)
- `endpoint` — the path to poll, e.g. `/v6/demo/latest/USD`
- `response_check` — a lambda that returns `True` if the response looks valid

For the `FileSensor`, set `mode="reschedule"` so it releases the worker slot
while it waits rather than blocking it.

</details>

<details>
<summary>✅ Answer — Sensor tasks</summary>

```python
check_api_availability = HttpSensor(
    task_id="check_api_availability",
    http_conn_id="forex_api",
    endpoint="/v6/latest/USD",
    request_params={"apikey": os.environ.get("FOREX_API_KEY", "demo")},
    response_check=lambda response: response.json().get("result") == "success",
    poke_interval=5,
    timeout=20,
)

check_config_file = FileSensor(
    task_id="check_config_file",
    filepath=CONFIG_FILE,              # "/tmp/forex/currencies.json"
    poke_interval=5,
    timeout=60,
    mode="reschedule",                 # releases the worker slot while waiting
)
```

</details>

**Test this phase:**
```bash
airflow tasks test forex_etl_pipeline check_api_availability 2024-01-15
airflow tasks test forex_etl_pipeline check_config_file 2024-01-15
```

---

## Phase 3 — Fetch the Rates

Add `fetch_forex_rates` — the task that calls the API and pushes the results
into XCom for downstream tasks to use.

<details>
<summary>💡 Hint — HttpHook and XCom</summary>

Use `HttpHook` (not `requests.get`) so Airflow manages the connection details
(host, timeout, headers) from the stored connection.

Push results with `context["ti"].xcom_push(key="rates", value=selected_rates)`.

Pull them later with `context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")`.

</details>

<details>
<summary>✅ Answer — fetch_forex_rates callable</summary>

```python
def fetch_forex_rates(**context):
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    base_currency = config.get("base", "USD")
    currencies = config.get("currencies", TARGET_CURRENCIES)

    hook = HttpHook(method="GET", http_conn_id="forex_api")
    response = hook.run(
        endpoint=f"/v6/{os.environ.get('FOREX_API_KEY', 'demo')}/latest/{base_currency}",
    )
    data = response.json()

    if data.get("result") != "success":
        raise ValueError(f"API error: {data.get('error-type', 'unknown')}")

    all_rates = data["conversion_rates"]
    selected_rates = {c: all_rates[c] for c in currencies if c in all_rates}

    context["ti"].xcom_push(key="rates", value=selected_rates)
    context["ti"].xcom_push(key="base_currency", value=base_currency)
    return selected_rates
```

</details>

**Test:**
```bash
export FOREX_API_KEY=your_key_here
airflow tasks test forex_etl_pipeline fetch_forex_rates 2024-01-15
```

---

## Phase 4 — Transform, Load, and Notify

Add the remaining tasks: write CSV, create the table, insert rows, send the
email summary, and clean up.

### 4a — Write to CSV

<details>
<summary>💡 Hint — CSV path and XCom pull</summary>

Pull rates from XCom using `task_ids="fetch_forex_rates"` and key `"rates"`.
Use `context["ds_nodash"]` (e.g. `"20240115"`) to make the filename date-specific.
Push the final path back to XCom with key `"csv_path"` — the loader task will need it.

</details>

<details>
<summary>✅ Answer — save_rates_to_csv callable</summary>

```python
def save_rates_to_csv(**context):
    execution_date = context["ds_nodash"]
    rates = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")
    base_currency = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="base_currency")

    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    csv_path = f"{DATA_DIR}/forex_rates_{execution_date}.csv"

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["base_currency", "target_currency", "rate", "fetched_at"],
        )
        writer.writeheader()
        for target_currency, rate in rates.items():
            writer.writerow({
                "base_currency": base_currency,
                "target_currency": target_currency,
                "rate": rate,
                "fetched_at": context["ts"],
            })

    context["ti"].xcom_push(key="csv_path", value=csv_path)
    return csv_path
```

</details>

### 4b — Create the Table

<details>
<summary>💡 Hint — PostgresOperator SQL</summary>

Use `CREATE TABLE IF NOT EXISTS` so the task is idempotent — running it 100 times
has the same effect as running it once.

</details>

<details>
<summary>✅ Answer — PostgresOperator</summary>

```python
create_forex_table = PostgresOperator(
    task_id="create_forex_table",
    postgres_conn_id="forex_postgres",
    sql="""
        CREATE TABLE IF NOT EXISTS forex_rates (
            id               SERIAL PRIMARY KEY,
            base_currency    VARCHAR(10)    NOT NULL,
            target_currency  VARCHAR(10)    NOT NULL,
            rate             NUMERIC(20, 8) NOT NULL,
            fetched_at       TIMESTAMP      NOT NULL,
            execution_date   DATE           NOT NULL DEFAULT '{{ ds }}'::DATE
        );
        CREATE INDEX IF NOT EXISTS idx_forex_rates_date
            ON forex_rates(execution_date);
    """,
)
```

</details>

### 4c — Insert Rows

<details>
<summary>💡 Hint — PostgresHook cursor</summary>

`PostgresHook(postgres_conn_id="forex_postgres").get_conn()` gives you a raw
psycopg2 connection. Loop over the CSV rows and call `cursor.execute(INSERT ...)`.
Use `ON CONFLICT DO NOTHING` so re-runs don't raise duplicate-key errors.

</details>

<details>
<summary>✅ Answer — load_rates_to_postgres callable</summary>

```python
def load_rates_to_postgres(**context):
    csv_path = context["ti"].xcom_pull(task_ids="save_rates_to_csv", key="csv_path")
    if not csv_path or not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    hook = PostgresHook(postgres_conn_id="forex_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    rows_inserted = 0

    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            cursor.execute(
                """
                INSERT INTO forex_rates
                    (base_currency, target_currency, rate, fetched_at, execution_date)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (row["base_currency"], row["target_currency"],
                 float(row["rate"]), row["fetched_at"], context["ds"]),
            )
            rows_inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    context["ti"].xcom_push(key="rows_inserted", value=rows_inserted)
```

</details>

---

## Phase 5 — Wire the Dependencies

With all tasks defined, connect them in the correct order.

<details>
<summary>💡 Hint — dependency syntax</summary>

Use `>>` to express "must run before". For two tasks that both feed into a third,
wrap them in a list: `[task_a, task_b] >> task_c`.

</details>

<details>
<summary>✅ Answer — dependency chain</summary>

```python
[check_api_availability, check_config_file] >> fetch_rates
fetch_rates >> write_csv >> create_forex_table >> insert_rates >> send_notification >> cleanup
```

</details>

**Full DAG test:**
```bash
airflow dags test forex_etl_pipeline 2024-01-15
```

**Verify data was loaded:**
```bash
docker exec -it forex-postgres psql -U airflow -d forex -c \
  "SELECT base_currency, target_currency, rate FROM forex_rates ORDER BY target_currency;"
```

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `Connection refused` on Postgres | Wrong host in connection | Use `localhost` (local Docker), not container name |
| `FileNotFoundError` for currencies.json | Config file missing | Run the `mkdir + cat` command from Phase 1b |
| HttpSensor times out | API key not set | Set `FOREX_API_KEY` env variable; free key from exchangerate-api.com |
| Duplicate key on re-run | `ON CONFLICT` not set | Ensure the INSERT uses `ON CONFLICT DO NOTHING` |
| `No module named 'psycopg2'` | Provider not installed | Run `pip install apache-airflow-providers-postgres` |

---

⬅️ **Prev:** [02 — Architecture](./02_ARCHITECTURE.md) &nbsp;&nbsp; ➡️ **Next:** [04 — Recap](./04_RECAP.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
