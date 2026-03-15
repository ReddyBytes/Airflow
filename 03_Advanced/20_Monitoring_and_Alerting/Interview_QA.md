# 20 — Monitoring and Alerting: Interview Q&A

---

**Q1. How do you monitor an Apache Airflow 3 cluster in production?**

Monitoring Airflow involves three layers. First, cluster health: Airflow emits StatsD metrics (scheduler heartbeat, task duration, DAG parse time) that you collect with a statsd-exporter, scrape with Prometheus, and visualize in Grafana. Second, component liveness: the `/health` endpoint on the webserver returns JSON with the status of the scheduler, triggerer, and metadata database — use this in Kubernetes liveness probes and external uptime monitors. Third, task-level alerts: use `on_failure_callback` at the DAG level to send Slack or PagerDuty alerts when specific tasks fail.

---

**Q2. What metrics does Airflow emit and through what protocol?**

Airflow emits metrics using the **StatsD protocol** (UDP datagrams). Key categories include: scheduler health (`scheduler_heartbeat`, `scheduler.tasks.starving`, `scheduler.critical_section_duration`), task lifecycle (`ti.start`, `ti.finish`, `task_duration`), and DAG processing (`dag_processing.total_parse_time`, `dag.loading_duration`). Configure StatsD output via the `[metrics]` section in `airflow.cfg` or via `AIRFLOW__METRICS__STATSD_*` environment variables.

---

**Q3. What is the Airflow health endpoint and what does it return?**

The `/health` endpoint is a GET endpoint on the Airflow webserver (default port 8080). It returns a JSON object with the status of three components: `metadatabase` (database connectivity), `scheduler` (last heartbeat timestamp and health status), and `triggerer` (last heartbeat timestamp and health status). Status values are `"healthy"` or `"unhealthy"`. It's the fastest way to check if Airflow is up and functioning.

---

**Q4. How do you set up Prometheus to scrape Airflow metrics?**

Use the `prom/statsd-exporter` container as an intermediary:
1. Configure Airflow to send StatsD metrics to `statsd-exporter:8125`.
2. `statsd-exporter` receives the StatsD UDP datagrams and exposes them as Prometheus-format metrics on port 9102 at `/metrics`.
3. Add a scrape config to `prometheus.yml` pointing at `statsd-exporter:9102`.

Prometheus then scrapes the endpoint every `scrape_interval` seconds and stores the time-series data.

---

**Q5. What Grafana panels should you build for an Airflow dashboard?**

The most important panels are: scheduler heartbeat rate (alert if it goes to zero), task failure rate per hour, average task duration (track trends over time to catch slowdowns), DAG processing total parse time (alert if DAGs start taking too long to load), and number of queued/waiting tasks (alert if a backlog builds up). A good dashboard shows both current state (gauges) and trends over time (time-series graphs).

---

**Q6. How do you alert on DAG failures?**

Combine two approaches. For real-time task-level alerts, use `on_failure_callback` at the DAG level — this fires immediately when any task fails and can call Slack, PagerDuty, or email. For systemic pattern detection (e.g., failure rate increasing over the past hour), use Prometheus AlertManager rules that query the `airflow_ti_finish_total{state="failed"}` metric and alert when the rate exceeds a threshold. The callback approach gives you immediate, contextual alerts per DAG; Prometheus gives you cluster-wide trend alerts.

---

**Q7. How does Datadog or New Relic integrate with Airflow?**

Both Datadog and New Relic support the StatsD protocol natively. Point Airflow's StatsD output at the Datadog Agent or New Relic Infrastructure Agent by setting `statsd_host` to the agent's hostname and `statsd_port` to 8125. The agent collects the metrics and forwards them to the SaaS platform automatically. No statsd-exporter or Prometheus is needed — the pipeline is: Airflow → Agent → SaaS dashboard.

---

**Q8. What is the most critical Airflow metric to monitor and why?**

`scheduler_heartbeat`. If the scheduler stops heartbeating, no new tasks will be scheduled — your pipeline silently stops running. Tasks in flight may complete, but nothing new starts. This is a silent failure mode (no task-level failures, no callbacks) that can go unnoticed for hours. Set an alert that fires if the heartbeat rate drops to zero for more than 2 minutes. This one alert can save you from "why hasn't the pipeline run since 3am?" incidents.

---

## Navigation

**Prev:** [19 — Pools and Resources](../19_Pools_and_Resources/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [21 — Testing DAGs](../21_Testing_DAGs/Interview_QA.md)
