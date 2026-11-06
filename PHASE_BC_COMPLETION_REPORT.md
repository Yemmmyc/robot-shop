# Robot Shop — Phase B & C Completion Report

**Date & Time**: 2026-11-04 07:25 UTC  
**Scope**: Phase B (Workload Stabilisation & Probe Tuning) and Phase C (Helm Health Remediation)  
**Status**: **COMPLETED & VERIFIED**

---

## 1. Executive Summary

All objectives of Phase B and Phase C have been executed cleanly without downtime, without data loss, and without touching Capstone 1 (`voting-app`):
- **Helm Release Status**: Transitioned from `failed` (Revision 1) to **`deployed`** (Revision 2).
- **Capstone 1 Integrity**: Namespace `capstone` (`voting-app`) remains at Revision 4 (`deployed`) with **5/5 pods Running and healthy**.
- **Redis PVC Integrity**: `data-redis-0` remains **Bound** (`1Gi`, standard storage class, age 4d20h).
- **MySQL Database Integrity**: All **948,833 records** in `cities.cities` and the `ratings` database are intact and queryable.
- **Pod Health**: **12/12 pods in `robot-shop` are `1/1 Running`**, with zero crash-looping or flapping.
- **Windows Access Bridge**: `robot-shop-bridge.service` is actively proxying `http://localhost:8080` to the Kind control plane container.

---

## 2. Phase B Actions (Stabilisation & Probes)

1. **MySQL Readiness Probe**:
   - Added `mysqladmin ping -h 127.0.0.1` exec readiness probe in [`mysql-deployment.yaml`](file:///home/yemmm/projects/robot-shop/K8s/helm/templates/mysql-deployment.yaml#L30-L43).
   - Parameters: `initialDelaySeconds: 5`, `periodSeconds: 10`, `timeoutSeconds: 5`, `failureThreshold: 10`.
   - Verified that MySQL only marks itself ready after initialization and table loading complete.

2. **Shipping Service CPU & Readiness Tuning**:
   - Relaxed CPU limits from `200m` to `1000m` and requests to `200m` in [`shipping-deployment.yaml`](file:///home/yemmm/projects/robot-shop/K8s/helm/templates/shipping-deployment.yaml#L27-L43) while strictly maintaining memory limits (`1000Mi`).
   - Adjusted readiness probe to `initialDelaySeconds: 30`, `periodSeconds: 10`, `timeoutSeconds: 5`, `failureThreshold: 30` to accommodate JVM warm-up.

3. **Ratings Service Probe Flapping Fix**:
   - Added explicit `timeoutSeconds: 5` in [`ratings-deployment.yaml`](file:///home/yemmm/projects/robot-shop/K8s/helm/templates/ratings-deployment.yaml#L33-L42) to eliminate false 1-second timeout failures.

4. **Web Frontend NodePort Pinning**:
   - Explicitly configured `nodePort: 32521` in [`web-service.yaml`](file:///home/yemmm/projects/robot-shop/K8s/helm/templates/web-service.yaml#L8-L14) and [`values.yaml`](file:///home/yemmm/projects/robot-shop/K8s/helm/values.yaml#L64-L65) to ensure deterministic binding for `robot-shop-bridge.service`.

---

## 3. Phase C Actions (Helm Health Remediation)

1. **Pre-Upgrade Backup**:
   - Generated full Kubernetes resource snapshot before applying changes: `k8s-live-backup-preupgrade.yaml`.
2. **Template Validation & Dry-Run**:
   - Validated template rendering (`helm template`) and performed dry-run upgrade (`helm upgrade --dry-run`).
3. **Helm Upgrade**:
   - Successfully executed `helm upgrade --install robot-shop K8s/helm -n robot-shop --timeout 10m`.
   - Result:
     ```text
     NAME        NAMESPACE   REVISION  UPDATED                                   STATUS    CHART
     robot-shop  robot-shop  2         2026-11-04 02:07:31.074787989 +0100 WAT   deployed  robot-shop-1.1.0
     voting-app  capstone    4         2026-10-21 09:29:58.20506289 +0100 WAT    deployed  voting-app-0.1.0
     ```

---

## 4. Verification & Health Audit

### Pod Status (`robot-shop` Namespace)
| Pod Name | Ready | Status | Restarts | Note |
|---|:---:|:---:|:---:|---|
| `cart-5dd7b45686-p58dg` | 1/1 | Running | 9 | Healthy |
| `catalogue-857b648bc7-h92ns` | 1/1 | Running | 9 | Healthy |
| `dispatch-86747877df-n9mvr` | 1/1 | Running | 16 | Healthy |
| `mongodb-69d9cf5747-57mbh` | 1/1 | Running | 9 | Healthy |
| `mysql-76d977dbd7-cp4hm` | 1/1 | Running | **0** | Upgraded with readiness probe |
| `payment-7cbd77fbb9-mjbqn` | 1/1 | Running | 9 | Healthy |
| `rabbitmq-876447689-rhfx8` | 1/1 | Running | 10 | Healthy |
| `ratings-7897d69b9b-8jcvr` | 1/1 | Running | **1** | Upgraded with 5s probe timeout |
| `redis-0` | 1/1 | Running | 9 | Bound to `data-redis-0` PVC |
| `shipping-6949d9fb5f-rwdgn` | 1/1 | Running | **0** | Upgraded with JVM CPU tuning |
| `user-75b5559997-p8drl` | 1/1 | Running | 11 | Healthy |
| `web-7649bf4886-rd47v` | 1/1 | Running | 22 | Healthy (Port 8080:32521) |

### End-to-End API Test Results
- `GET http://127.0.0.1:8080/` &rarr; `HTTP/1.1 200 OK`
- `GET /api/catalogue/categories` &rarr; `200 OK` (`["Artificial Intelligence","Robot"]`)
- `PUT /api/ratings/api/rate/Watson/5` &rarr; `200 OK` (`{"success":true}`)
- `GET /api/ratings/api/fetch/Watson` &rarr; `200 OK` (`{"avg_rating":5,"rating_count":1}`)
- `GET /api/user/uniqueid` &rarr; `200 OK` (`{"uuid":"anonymous-1"}`)
- `GET /api/cart/add/anonymous-1/Watson/1` &rarr; `200 OK` (`{"total":2001,...}`)
- `GET /api/shipping/codes` &rarr; `200 OK` (25 country codes returned)

