# Service Level Objectives (SLO) & Error Budget Policy
## Stan's Robot Shop — DevOps Capstone 2 (Keep It Running)

---

## 1. System Overview & Critical User Journeys

Stan's Robot Shop is a containerized microservices e-commerce application comprising 12 distributed components (web frontend, user, catalogue, cart, payment, shipping, ratings, dispatch, MySQL, MongoDB, Redis, and RabbitMQ).

To ensure customer satisfaction and operational resilience, SLOs are defined around four primary user journeys:

```
[Customer Browser]
       │
   (HTTP NodePort)
       ▼
   ┌───────┐      ┌───────────┐      ┌─────────┐
   │  web  ├─────►│ catalogue ├─────►│ MongoDB │ (Product Catalog)
   └───┬───┘      └───────────┘      └─────────┘
       │
       │          ┌───────────┐      ┌─────────┐
       ├─────────►│   cart    ├─────►│  Redis  │ (Active Session Cart)
       │          └─────┬─────┘      └─────────┘
       │                │
       │                ▼
       │          ┌───────────┐      ┌─────────┐
       ├─────────►│  payment  ├─────►│RabbitMQ │ (Order Processing & Dispatch)
       │          └───────────┘      └─────────┘
       │
       │          ┌───────────┐      ┌─────────┐
       └─────────►│ shipping  ├─────►│  MySQL  │ (Geo-Rates & Ratings)
                  └───────────┘      └─────────┘
```

1. **Product Browsing & Discovery**: Loading storefront assets, querying catalogue SKU data, and viewing product details.
2. **Cart Management**: Creating cart sessions, adding/updating items, and retrieving active cart totals.
3. **Shipping Calculation**: Looking up delivery cities and calculating shipping quotes based on weight and destination.
4. **Order Placement & Payment**: Submitting payment information, empty-cart validation, and triggering asynchronous dispatch.

---

## 2. Service Level Indicators (SLIs)

### 2.1 Availability SLI
The proportion of valid HTTP requests to Robot Shop microservices that return successful HTTP status codes (2xx or 3xx), excluding customer-caused errors (4xx client validation errors):

$$\text{SLI}_{\text{Availability}} = \frac{\sum \text{rate}(HTTP_{\text{status} \in [200, 399]}[t])}{\sum \text{rate}(HTTP_{\text{all}}[t]) - \sum \text{rate}(HTTP_{\text{status} \in [400, 499]}[t])}$$

* **Metric Source**: Microservice ingress logs (Fluent Bit/Loki) and HTTP server Prometheus metrics (`http_requests_total`).
* **Good Events**: Responses with HTTP status 200–399.
* **Bad Events**: Responses with HTTP status 500–599, dropped connections, and gateway timeouts (502, 503, 504).
* **Excluded Events**: Client-side validation rejections (HTTP 400 Bad Request, HTTP 404 Not Found, HTTP 422 Unprocessable Entity).

### 2.2 Latency SLI
The proportion of successful HTTP requests that complete within acceptable responsiveness thresholds:

$$\text{SLI}_{\text{Latency}} = \frac{\sum \text{rate}(HTTP_{\text{duration} \le 1500\text{ms}}[t])}{\sum \text{rate}(HTTP_{\text{status} \in [200, 399]}[t])}$$

* **Metric Source**: OpenTelemetry trace span durations and Prometheus histogram buckets (`http_request_duration_seconds_bucket`).
* **Threshold Targets**:
  * P95 user-facing transaction latency: $\le 1,500\text{ ms}$
  * P95 internal health check probes: $\le 500\text{ ms}$

---

## 3. Service Level Objectives (SLOs)

| Service Level Objective | SLI Metric | Target | Measurement Window |
| :--- | :--- | :--- | :--- |
| **Storefront Availability** | Successful HTTP response ratio | **$\ge 99.0\%$** | 30-day rolling window |
| **Transaction Latency** | HTTP round-trip latency $\le 1.5\text{s}$ | **$\ge 95.0\%$** | 30-day rolling window |
| **Core Datastore Uptime** | MySQL & Redis socket availability | **$\ge 99.5\%$** | 30-day rolling window |

---

## 4. Error Budget Calculations (30-Day Rolling Window)

The Error Budget represents the allowable margin of imperfection over a standard 30-day measurement window:

$$\text{Error Budget} = 1.0 - \text{SLO Target} = 1.0 - 0.990 = 0.010 \quad (1.0\%)$$

### Time-Based Budget:
* **Total Time in 30 Days**: $30 \text{ days} \times 24 \text{ hours} \times 60 \text{ minutes} = 43,200 \text{ minutes}$ ($2,592,000 \text{ seconds}$)
* **Maximum Allowed Downtime (1.0%)**:
  $$43,200 \text{ minutes} \times 0.010 = \mathbf{432 \text{ minutes}} \quad (7 \text{ hours}, 12 \text{ minutes})$$

### Request-Based Budget:
For a nominal traffic rate of 1,000,000 customer interactions per month:
* **Allowable Failed Requests**: $1,000,000 \times 0.010 = \mathbf{10,000 \text{ failed requests}}$
* **Required Successful Requests**: $\mathbf{990,000 \text{ successful requests}}$

---

## 5. Multi-Window, Multi-Burn-Rate Alerting Strategy

Rather than alerting on simple point-in-time failure spikes, we implement Google SRE multi-window, multi-burn-rate alerting to protect against budget depletion while preventing alert fatigue:

$$\text{Burn Rate (BR)} = \frac{\text{Current Error Rate}}{\text{Allowed Error Budget Rate}} = \frac{1 - \text{Availability}}{0.01}$$

| Alert Level | Burn Rate (BR) | % Budget Consumed | Long Window | Short Window | Time to 100% Depletion | Action / Routing |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SEV-1 (Critical)** | **$14.4\times$** | **$2.0\%$** | 1 hour | 5 minutes | 50.0 hours (2.1 days) | Page on-call; Slack `#devops-alerts` |
| **SEV-2 (Major)** | **$6.0\times$** | **$5.0\%$** | 6 hours | 30 minutes | 120.0 hours (5.0 days) | File urgent ticket; Slack notification |
| **SEV-3 (Warning)** | **$1.0\times$** | **$10.0\%$** | 3 days | 6 hours | 720.0 hours (30 days) | Normal review; daily standup report |

### Alert Definitions (PromQL Implementation):
```promql
# 14.4x Burn Rate Alert (Consumes 2% of budget in 1 hour)
(
  sum(rate(http_requests_total{namespace="robot-shop",status=~"5.."}[1h]))
  /
  sum(rate(http_requests_total{namespace="robot-shop"}[1h]))
) > (14.4 * 0.01)
and
(
  sum(rate(http_requests_total{namespace="robot-shop",status=~"5.."}[5m]))
  /
  sum(rate(http_requests_total{namespace="robot-shop"}[5m]))
) > (14.4 * 0.01)
```

---

## 6. Error Budget Policy & Escalation Matrix

When errors consume disproportionate amounts of the monthly budget, operational priorities automatically shift according to the following policy:

| Remaining Budget | Operational State | Engineering Action |
| :--- | :--- | :--- |
| **$> 50\%$** | **Normal Operation (Green)** | Regular feature releases and product deployments proceed unhindered. |
| **$25\% - 50\%$** | **Degraded State (Yellow)** | Deployments require senior peer review. Reliability bugs prioritized in sprint backlog. |
| **$< 25\%$** | **Critical State (Orange)** | High-risk architectural changes frozen. Non-essential background tasks throttled. |
| **$\le 0\%$ (Breached)** | **Budget Exhausted (Red)** | **Full feature deployment freeze.** All development resources pivot to reliability engineering, root-cause resolution, and infrastructure resilience until the rolling 30-day window replenishes the budget. |

---

## 7. Notification Routing & Runbook Links

All alerts generated by the Prometheus alerting pipeline are routed through Alertmanager to the designated incident channel:
* **Slack Channel**: `#devops-alerts`
* **Target Webhook**: Configured in [`observability/alerting/alerts.yaml`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/observability/alerting/alerts.yaml)
* **Linked SRE Runbook**: Every notification includes a direct markdown link to the remediation procedures in [`RUNBOOK.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/RUNBOOK.md).

