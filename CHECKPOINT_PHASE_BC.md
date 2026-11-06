# Robot Shop — Phase B & C Resume Checkpoint

**Timestamp**: 2026-11-03 23:38 UTC  
**Status**: Phase A Assessment Complete & Approved. Ready to execute Phase B (Stabilisation) & Phase C (Helm Health Remediation) immediately upon reboot.

---

## 1. Safety & Preservation Verification
- **Kind Cluster**: `capstone-cluster` (v1.32.2) — Preserved.
- **Capstone 1**: Namespace `capstone` (`voting-app`), 5/5 pods running, revision 4 deployed — Completely untouched.
- **Redis PVC**: `data-redis-0` (Bound, 1Gi) — Untouched.
- **MySQL Database**: `cities` (948,833 records) and `ratings` database — Untouched and verified.
- **Helm Backups**:
  - Original: `K8s/helm.backup/`
  - Timestamped backup created: `K8s/helm.backup-20261103_232215/`

---

## 2. Completed Diagnostics & Test Results
- **12/12 Pods Running**: `cart`, `catalogue`, `dispatch`, `mongodb`, `mysql`, `payment`, `rabbitmq`, `ratings`, `redis-0`, `shipping`, `user`, `web`.
- **Network Bridge**: `robot-shop-bridge.service` listening on `127.0.0.1:8080`, target `172.24.0.2:32521`.
- **API Tests Verified**:
  - `GET /api/catalogue/categories` -> 200 OK (`["Artificial Intelligence","Robot"]`)
  - `PUT /api/ratings/api/rate/Watson/5` -> 200 OK (`{"success":true}`)
  - `GET /api/ratings/api/fetch/Watson` -> 200 OK (`{"avg_rating":5,"rating_count":1}`)
  - `GET /api/user/uniqueid` -> 200 OK (`{"uuid":"anonymous-1"}`)
  - `GET /api/cart/add/anonymous-1/Watson/1` -> 200 OK (`{"total":2001,...}`)
  - `GET /api/shipping/codes` -> 200 OK (25 country codes returned)

---

## 3. Immediate Action Plan Upon Restart
Once the laptop restarts and Docker Desktop/WSL are running:

1. **Verify Services**:
   - Confirm Docker and Kind control-plane container are running.
   - Confirm `robot-shop-bridge.service` is active.
   - Capture live K8s snapshot: `kubectl get all,pvc,pv,configmap,secret -n robot-shop -o yaml > k8s-live-backup-preupgrade.yaml`.

2. **Phase B Implementation (Probes & CPU Tuning)**:
   - Add MySQL `readinessProbe` using `mysqladmin ping -h 127.0.0.1` (no exposed credentials, local socket/loopback check).
   - Adjust Shipping readiness probe:
     - Increase `initialDelaySeconds: 30`, `periodSeconds: 10`, `timeoutSeconds: 5`, `failureThreshold: 30`.
     - Relax CPU throttling (`requests.cpu: 200m`, `limits.cpu: 1000m`) while strictly keeping memory limits unchanged (`1000Mi`).
   - Add safe `timeoutSeconds: 5` to Ratings readiness probe to avoid 1-second timeout flapping.

3. **Phase C Implementation (Helm Health Remediation)**:
   - Run `helm template` and inspect diff against live state to ensure zero impact on PVCs or databases.
   - Run `helm upgrade --install robot-shop K8s/helm -n robot-shop --timeout 10m` to transition release status from `failed` to `deployed`.
   - Verify all 12 pods, endpoints, and confirm Capstone 1 is completely healthy.

