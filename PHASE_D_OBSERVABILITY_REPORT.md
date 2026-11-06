# Stan's Robot Shop — Observability & Monitoring Report

**Generated**: 2026-11-04T20:01:01.963575+00:00  
**Namespace**: `robot-shop`  
**Overall Status**: ✅ **ALL SYSTEMS OPERATIONAL**  

---

## 1. Executive Summary

- **Kubernetes Node**: `capstone-cluster-control-plane` is **Ready** (Kubelet: `v1.32.2`).
- **Workloads**: **12/12 pods are 1/1 Running** in namespace `robot-shop`.
- **Databases**: MySQL is **ALIVE** (QPS: `0.995`), Redis is **ALIVE** (Memory: `850.27K`).
- **Storage**: PVC `data-redis-0` is **Bound**.
- **Active Alerts**: `0` active alerts.

---

## 2. Resource Utilization Baseline

| Resource Domain | Metric | Measured Value |
|---|---|---|
| **Host Memory (WSL)** | Total RAM | `4920 MB` |
| **Host Memory (WSL)** | Used RAM | `2793 MB` (56.8%) |
| **Host Memory (WSL)** | Available RAM | `1889 MB` |
| **Kind Control Plane** | Docker CPU / Mem | `36.71%` / `2.485GiB / 4.805GiB` |

---

## 3. Workload Health & Restart Telemetry

| Pod Name | Ready | Phase | Total Restarts | Session Restarts | Pod IP |
|---|:---:|:---:|:---:|:---:|---|
| `cart-5dd7b45686-p58dg` | ✅ 1/1 | Running | 15 | 0 | `10.244.0.3` |
| `catalogue-857b648bc7-h92ns` | ✅ 1/1 | Running | 15 | 0 | `10.244.0.15` |
| `dispatch-86747877df-n9mvr` | ✅ 1/1 | Running | 23 | 0 | `10.244.0.13` |
| `mongodb-69d9cf5747-57mbh` | ✅ 1/1 | Running | 15 | 0 | `10.244.0.7` |
| `mysql-76d977dbd7-cp4hm` | ✅ 1/1 | Running | 6 | 0 | `10.244.0.5` |
| `payment-7cbd77fbb9-mjbqn` | ✅ 1/1 | Running | 15 | 0 | `10.244.0.16` |
| `rabbitmq-876447689-rhfx8` | ✅ 1/1 | Running | 16 | 0 | `10.244.0.12` |
| `ratings-7897d69b9b-8jcvr` | ✅ 1/1 | Running | 9 | 0 | `10.244.0.9` |
| `redis-0` | ✅ 1/1 | Running | 15 | 0 | `10.244.0.19` |
| `shipping-6949d9fb5f-rwdgn` | ✅ 1/1 | Running | 7 | 0 | `10.244.0.21` |
| `user-75b5559997-p8drl` | ✅ 1/1 | Running | 17 | 0 | `10.244.0.20` |
| `web-7649bf4886-rd47v` | ✅ 1/1 | Running | 35 | 0 | `10.244.0.8` |

### Deployments Status
| Deployment | Desired | Ready | Available | Status |
|---|:---:|:---:|:---:|:---:|
| `cart` | 1 | 1 | 1 | ✅ Healthy |
| `catalogue` | 1 | 1 | 1 | ✅ Healthy |
| `dispatch` | 1 | 1 | 1 | ✅ Healthy |
| `mongodb` | 1 | 1 | 1 | ✅ Healthy |
| `mysql` | 1 | 1 | 1 | ✅ Healthy |
| `payment` | 1 | 1 | 1 | ✅ Healthy |
| `rabbitmq` | 1 | 1 | 1 | ✅ Healthy |
| `ratings` | 1 | 1 | 1 | ✅ Healthy |
| `shipping` | 1 | 1 | 1 | ✅ Healthy |
| `user` | 1 | 1 | 1 | ✅ Healthy |
| `web` | 1 | 1 | 1 | ✅ Healthy |

---

## 4. Databases & Persistence Health

### MySQL Health
- **Availability**: `ALIVE` (via `mysqladmin ping -h 127.0.0.1`)
- **Uptime**: `15464 seconds`
- **Active Threads**: `11`
- **Total Questions**: `15396`
- **Slow Queries**: `0`
- **Average QPS**: `0.995`

### Redis Health
- **Availability**: `PONG` (via `redis-cli ping`)
- **Version**: `4.0.6`
- **Memory Usage**: `850.27K` (Fragmentation Ratio: `3.98`)
- **Connected Clients**: `3`
- **Commands Processed**: `14` (`0 ops/sec`)
- **RDB Persistence Status**: `ok`

---

## 5. Application Probes & Prometheus Metrics

### Synthetic HTTP Probes
| Service | Path | Status Code | Latency (ms) | Result |
|---|---|:---:|:---:|:---:|
| **Web Frontend** | `/` | `200` | `5.9 ms` | ✅ OK |
| **Cart Health** | `/api/cart/health` | `200` | `9.45 ms` | ✅ OK |
| **Catalogue Health** | `/api/catalogue/health` | `200` | `5.41 ms` | ✅ OK |
| **User UniqueID** | `/api/user/uniqueid` | `200` | `10.07 ms` | ✅ OK |
| **Shipping Codes** | `/api/shipping/codes` | `200` | `28.12 ms` | ✅ OK |
| **Payment Health** | `/api/payment/health` | `200` | `4.89 ms` | ✅ OK |
| **Cart Metrics** | `/api/cart/metrics` | `200` | `5.16 ms` | ✅ OK |
| **Payment Metrics** | `/api/payment/metrics` | `200` | `6.5 ms` | ✅ OK |

### Prometheus-Format Metrics
- **Cart Service** (`/api/cart/metrics`): `items_added` = `0.0`
- **Payment Service** (`/api/payment/metrics`): `sold_count_total` = `0.0`
- **Shipping Service** (`/actuator/health`): Status = `UP`

---

## 6. Alerting & Threshold Verification

✅ **All threshold checks passed cleanly.** Zero active alerts.

---

## 7. How to Operate Monitoring

### On-Demand Status
```bash
python3 scripts/robot_shop_monitor.py --status
```

### Continuous Watch Mode
```bash
python3 scripts/robot_shop_monitor.py --watch --interval 10
```

### Automated Alert Checking (CI / Scripting)
```bash
python3 scripts/robot_shop_monitor.py --check-alerts
# Returns exit code: 0 = OK, 1 = WARNING, 2 = CRITICAL
```

### Generate Report & JSON Snapshot
```bash
python3 scripts/robot_shop_monitor.py --report
```