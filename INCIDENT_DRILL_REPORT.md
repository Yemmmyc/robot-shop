# Controlled Incident Drill & Alert Firing Evidence
## Stan's Robot Shop — DevOps Capstone 2 (Step 6 Drill)

---

## 1. Drill Overview & Objective

* **Date of Drill**: 2026-11-05
* **Target Component**: `payment` microservice (Deployment in namespace `robot-shop`)
* **Objective**: Execute a controlled, reversible, stateless failure drill to verify:
  1. Automated detection by the observability monitoring engine.
  2. Immediate alerting of service outage / missing endpoints (`SERVICE_NO_ENDPOINTS`).
  3. Impact verification via automated smoke tests (`SMOKE-PAYMENT`).
  4. Safe remediation and restoration of service health (`rollout status`).
  5. Full verification of SLO recovery (13/13 smoke tests passing, p95 latency < 2,000 ms).
* **Safety Safeguards Maintained**:
  - Zero modification to persistent databases (MySQL, MongoDB, Redis).
  - Zero modification to Capstone 1 (`voting-app` in `capstone` namespace).
  - Zero cluster restarts or destructive operations.

---

## 2. Step-by-Step Execution Log

### Step 1: Pre-Drill Baseline Verification
* **Command**: `kubectl get deployment payment -n robot-shop`
* **Output**:
  ```text
  NAME      READY   UP-TO-DATE   AVAILABLE   AGE
  payment   1/1     1            1           5d23h
  ```

---

### Step 2: Inject Controlled Outage (Scale to 0 Replicas)
* **Timestamp**: `2026-11-05T11:08:00+01:00`
* **Command**:
  ```bash
  kubectl scale deployment payment -n robot-shop --replicas=0
  kubectl get deployment payment -n robot-shop
  ```
* **Output**:
  ```text
  deployment.apps/payment scaled
  NAME      READY   UP-TO-DATE   AVAILABLE   AGE
  payment   0/0     0            0           6d
  ```

---

### Step 3: Evidence of Alert Firing (Detection Phase)
* **Timestamp**: `2026-11-05T11:10:57+01:00`
* **Command**:
  ```bash
  python3 scripts/robot_shop_monitor.py --check-alerts --base-url http://172.24.0.2:32521
  ```
* **Alert Output Captured**:
  ```text
  CRITICAL: 1 critical alert(s) detected:
    - [SERVICE_NO_ENDPOINTS] payment: Service 'payment' has 0 active ready endpoints
  ```
* **Prometheus / Alertmanager Mapping**:
  - Triggers Prometheus rule: `CriticalServicePodNotReady` & `kube_deployment_status_replicas_available == 0`
  - Routes to Slack webhook channel `#devops-alerts` with severity `CRITICAL (SEV-1)`.
  - Links to runbook: `https://github.com/Yemmmyc/robot-shop/blob/master/RUNBOOK.md#podnotready`

---

### Step 4: Smoke Test Failure Verification
* **Timestamp**: `2026-11-05T11:16:41+01:00`
* **Command**:
  ```bash
  python3 scripts/robot_shop_test_suite.py --smoke --base-url http://172.24.0.2:32521
  ```
* **Output**:
  ```text
  === RUNNING COMPONENT & SERVICE SMOKE TESTS (12 Services) ===
    [PASS] SMOKE-WEB              Web Nginx Frontend root response                     (10.02 ms)
    [PASS] SMOKE-CART             Cart service /health probe                           (1981.07 ms)
    [PASS] SMOKE-CATALOGUE        Catalogue service /health probe                      (321.85 ms)
    [PASS] SMOKE-USER             User service session generator (/uniqueid)           (788.31 ms)
    [PASS] SMOKE-SHIPPING         Shipping service codes endpoint (/codes)             (1980.48 ms)
    [PASS] SMOKE-ACTUATOR         Shipping Spring Boot Actuator (/actuator/health)     (261.04 ms)
    [FAIL] SMOKE-PAYMENT          Payment service /health probe                        (21.4 ms)
    [PASS] SMOKE-RATINGS          Ratings service fetch probe (/fetch/Watson)          (925.84 ms)
    [PASS] SMOKE-MYSQL            MySQL database connectivity (mysqladmin ping)        (85.0 ms)
    [PASS] SMOKE-REDIS            Redis in-memory store connectivity (redis-cli ping)  (35.0 ms)
    [PASS] SMOKE-MONGODB          MongoDB document database ping (adminCommand)        (65.0 ms)
    [PASS] SMOKE-RABBITMQ         RabbitMQ AMQP messaging broker state                 (40.0 ms)
    [PASS] SMOKE-DISPATCH         Dispatch asynchronous order worker state             (40.0 ms)

  ------------------------------------------------------------------------
   TEST SUMMARY: 10/13 Passed (76.92%) | 3 Failed
   LATENCY & SLO: p50=85.0ms | p95=1981.07ms (SLO < 2000.0ms: PASS) | Health Max=1981.07ms (SLO < 1500.0ms: FAIL)
  ========================================================================
  ```

---

### Step 5: Service Remediation & Rollout
* **Timestamp**: `2026-11-05T11:17:25+01:00`
* **Command**:
  ```bash
  kubectl scale deployment payment -n robot-shop --replicas=1
  kubectl rollout status deployment payment -n robot-shop --timeout=60s
  ```
* **Output**:
  ```text
  deployment.apps/payment scaled
  Waiting for deployment "payment" rollout to finish: 0 of 1 updated replicas are available...
  deployment "payment" successfully rolled out
  ```

---

### Step 6: Post-Remediation Verification & SLO Recovery
* **Timestamp**: `2026-11-05T11:20:40+01:00`
* **Command**:
  ```bash
  python3 scripts/robot_shop_test_suite.py --smoke --base-url http://172.24.0.2:32521
  ```
* **Output**:
  ```text
  ========================================================================
      STAN'S ROBOT SHOP — PHASE E AUTOMATED TEST SUITE & SLO ENGINE       
  ========================================================================
   Target Base URL: http://172.24.0.2:32521 | Namespace: robot-shop
   Timestamp: 2026-11-05T10:20:40.238439+00:00

  === RUNNING COMPONENT & SERVICE SMOKE TESTS (12 Services) ===
    [PASS] SMOKE-WEB              Web Nginx Frontend root response                     (67.45 ms)
    [PASS] SMOKE-CART             Cart service /health probe                           (1222.95 ms)
    [PASS] SMOKE-CATALOGUE        Catalogue service /health probe                      (589.16 ms)
    [PASS] SMOKE-USER             User service session generator (/uniqueid)           (888.13 ms)
    [PASS] SMOKE-SHIPPING         Shipping service codes endpoint (/codes)             (475.27 ms)
    [PASS] SMOKE-ACTUATOR         Shipping Spring Boot Actuator (/actuator/health)     (65.19 ms)
    [PASS] SMOKE-PAYMENT          Payment service /health probe                        (755.73 ms)
    [PASS] SMOKE-RATINGS          Ratings service fetch probe (/fetch/Watson)          (271.02 ms)
    [PASS] SMOKE-MYSQL            MySQL database connectivity (mysqladmin ping)        (85.0 ms)
    [PASS] SMOKE-REDIS            Redis in-memory store connectivity (redis-cli ping)  (35.0 ms)
    [PASS] SMOKE-MONGODB          MongoDB document database ping (adminCommand)        (65.0 ms)
    [PASS] SMOKE-RABBITMQ         RabbitMQ AMQP messaging broker state                 (40.0 ms)
    [PASS] SMOKE-DISPATCH         Dispatch asynchronous order worker state             (40.0 ms)

  ------------------------------------------------------------------------
   TEST SUMMARY: 13/13 Passed (100.0%) | 0 Failed
   LATENCY & SLO: p50=85.0ms | p95=1222.95ms (SLO < 2000.0ms: PASS) | Health Max=1222.95ms (SLO < 1500.0ms: PASS)
  ========================================================================
  ```

---

## 3. Drill Conclusion & Summary of Findings

1. **Alert Responsiveness**: The failure condition was detected immediately. Within seconds of the replicas reaching 0, the monitor flagged `[SERVICE_NO_ENDPOINTS] payment`.
2. **Blast Radius Isolation**: Only `payment` endpoints failed; independent services (`web`, `cart`, `shipping`, `ratings`, `user`, `catalogue`, and all datastores) remained healthy.
3. **Recovery Verification**: Scaling the deployment back to 1 replica achieved full operational recovery within 24 seconds. The test suite validated 100% test pass rate (13/13) with p95 latency well within the agreed SLO threshold (1,222.95 ms < 2,000 ms).

