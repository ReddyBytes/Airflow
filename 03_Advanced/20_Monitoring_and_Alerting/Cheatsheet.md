# 20 — Monitoring and Alerting: Cheatsheet

## Key StatsD Metrics

### Scheduler Health
| Metric | Type | Alert when |
|---|---|---|
| `airflow.scheduler_heartbeat` | Counter | Rate = 0 for > 2 minutes |
| `airflow.scheduler.tasks.starving` | Gauge | > 0 for sustained period |
| `airflow.scheduler.tasks.executable` | Gauge | > 50 queued tasks |
| `airflow.scheduler.critical_section_duration` | Timer | > 1 second |

### Task Metrics
| Metric | Type | Notes |
|---|---|---|
| `airflow.task_duration` | Timer | Per DAG and task ID |
| `airflow.ti.finish.<dag>.<task>.<state>` | Counter | Break down by state |
| `airflow.ti.start.<dag>.<task>` | Counter | Task start events |
| `airflow.operator_successes_<Operator>` | Counter | Operator-level success tracking |
| `airflow.operator_failures_<Operator>` | Counter | Alert on sudden increases |

### DAG Processing
| Metric | Type | Alert when |
|---|---|---|
| `airflow.dag_processing.total_parse_time` | Timer | > 30 seconds |
| `airflow.dag_processing.processes` | Gauge | Drops unexpectedly |
| `airflow.dag.loading_duration.<dag_id>` | Timer | Outlier DAGs slowing parsing |

---

## Health Endpoint

```
GET /health
```

Response format:
```json
{
  "metadatabase": {
    "status": "healthy"
  },
  "scheduler": {
    "status": "healthy",
    "latest_scheduler_heartbeat": "2024-01-15T10:30:00+00:00"
  },
  "triggerer": {
    "status": "healthy",
    "latest_triggerer_heartbeat": "2024-01-15T10:30:01+00:00"
  }
}
```

Status values: `"healthy"` | `"unhealthy"`

Use for: Kubernetes liveness probes, load balancer checks, uptime monitors.

---

## Prometheus Scrape Config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "airflow"
    static_configs:
      - targets: ["statsd-exporter:9102"]
    scrape_interval: 15s
```

---

## StatsD Configuration (airflow.cfg)

```ini
[metrics]
statsd_on     = True
statsd_host   = statsd-exporter
statsd_port   = 8125
statsd_prefix = airflow
```

Or via environment variables:
```bash
AIRFLOW__METRICS__STATSD_ON=True
AIRFLOW__METRICS__STATSD_HOST=statsd-exporter
AIRFLOW__METRICS__STATSD_PORT=8125
```

---

## Key Grafana Panels

| Panel title | PromQL query |
|---|---|
| Scheduler heartbeat rate | `rate(airflow_scheduler_heartbeat_total[5m])` |
| Task success rate (1h) | `rate(airflow_ti_finish_total{state="success"}[1h])` |
| Task failure rate (1h) | `rate(airflow_ti_finish_total{state="failed"}[1h])` |
| Average task duration | `avg(airflow_task_duration_seconds)` |
| DAG parse time | `airflow_dag_processing_total_parse_time_seconds` |
| Queued tasks | `airflow_scheduler_tasks_executable` |

---

## Alert Threshold Guide

| Component | Metric | Warning | Critical |
|---|---|---|---|
| Scheduler | Heartbeat gap | > 30s | > 2min |
| Tasks | Failure rate | > 2/hour | > 10/hour |
| DAG parsing | Total parse time | > 20s | > 60s |
| Queue | Tasks waiting | > 20 | > 100 |
| Task duration | Avg vs baseline | +50% | +200% |

---

## Monitoring Architecture (Summary)

```
Airflow (StatsD UDP) → statsd-exporter → Prometheus → Grafana/AlertManager
Airflow (/health HTTP) → Kubernetes liveness probe / uptime monitor
Airflow (callbacks) → Slack / PagerDuty / Email (task-level alerts)
```

---

## Navigation

**Prev:** [19 — Pools and Resources](../19_Pools_and_Resources/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [21 — Testing DAGs](../21_Testing_DAGs/Cheatsheet.md)
