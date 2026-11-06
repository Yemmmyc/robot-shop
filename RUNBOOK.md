# SRE Operational Runbook: Stan's Robot Shop
## DevOps Capstone 2 — Incident Triage, Diagnosis & Remediation Guide

---

## 1. System Overview & Critical Architecture

Stan's Robot Shop is deployed on Kubernetes in the `robot-shop` namespace. It depends on several backing datastores and stateless microservices:

| Microservice | Technology | Primary Function | Upstream Dependency | Downstream Dependents |
| :--- | :--- | :--- | :--- | :--- |
| **`web`** | Nginx / Angular | Static UI & API Gateway proxy | Ingress / NodePort 32521 | Customer browsers |
| **`catalogue`** | Node.js | Product metadata & SKU catalog | MongoDB | `web` |
| **`user`** | Node.js | User profiles & authentication | MongoDB | `web` |
| **`cart`** | Node.js | Session carts & item totals | Redis | `web`, `payment` |
| **`shipping`** | Java Spring Boot | Distance, city rates & cost calculation | MySQL | `web`, `payment` |
| **`ratings`** | Node.js / PHP | Product ratings & customer reviews | MySQL | `web` |
| **`payment`** | Python (Flask) | Order checkout & transaction authorization | `cart`, `shipping`, RabbitMQ | `web` |
| **`dispatch`** | Go | Order queue dispatch & fulfillment worker | RabbitMQ | Backend message queue |
| **`mysql`** | MySQL 5.7 | Relational databases (`cities`, `ratings`) | PersistentVolumeClaim | `shipping`, `ratings` |
| **`mongodb`** | MongoDB 3.4 | NoSQL document database (`catalog`, `users`) | Local filesystem | `catalogue`, `user` |
| **`redis`** | Redis 4.0 | In-memory key-value session cache | Local filesystem | `cart` |
| **`rabbitmq`** | RabbitMQ 3.7 | AMQP message broker for order processing | Network / socket | `payment`, `dispatch` |

---

## 2. Emergency First Steps (SEV-1 / SEV-2 Incidents)

When paged via Slack `#devops-alerts` or an automated burn-rate alert fires:

1. **Acknowledge the Alert**: Post acknowledgment in `#devops-alerts` with incident responder name.
2. **Assess Cluster & Node Health**:
   ```bash
   kubectl get nodes -o wide
   kubectl top nodes || wsl -d Ubuntu-22.04 -e bash -c "free -m; uptime"
   ```
3. **Inspect Pod Health across Namespaces**:
   ```bash
   kubectl get pods -n robot-shop -o wide
   kubectl get pods -n capstone -o wide
   ```
4. **Run Automated Telemetry Check**:
   ```bash
   python3 scripts/robot_shop_monitor.py --check-alerts --base-url http://172.24.0.2:32521
   ```

---

## 3. Alert Triage & Remediation Procedures

### 3.1 Alert: `RobotShopAvailabilityBreach` (Critical & Warning)
* **Severity**: `critical` (SEV-1) for 14.4x burn rate; `warning` (SEV-2) for 6x burn rate.
* **SLI Impact**: Overall HTTP success rate has dropped below the 99.0% SLO target.
* **Diagnostic Steps**:
  1. Identify which microservice is serving 5xx responses:
     ```bash
     kubectl logs -n robot-shop -l app=web --tail=100 | grep -E "HTTP/[0-9.]+ 5"
     ```
  2. Execute the smoke test suite to pinpoint broken downstream paths:
     ```bash
     python3 scripts/robot_shop_test_suite.py --smoke --base-url http://172.24.0.2:32521
     ```
  3. Verify datastore connectivity (MySQL, Redis, MongoDB):
     ```bash
     # Check Redis ping
     kubectl exec -n robot-shop redis-0 -- redis-cli ping
     # Check MySQL connection
     kubectl exec -n robot-shop deployment/mysql -- mysqladmin -uroot -probotshop ping
     ```
* **Remediation**:
  - If a single pod is throwing 5xx errors due to resource starvation, check memory limits:
    ```bash
    kubectl describe pod -n robot-shop <pod-name> | grep -i oom
    ```
  - If cart operations fail, verify Redis key-space and memory limits:
    ```bash
    kubectl exec -n robot-shop redis-0 -- redis-cli info memory
    ```

---

### 3.2 Alert: `HighHttpErrorRate`
* **Severity**: `critical` (5xx error rate > 1%).
* **Diagnostic Steps**:
  1. Inspect container logs for runtime exceptions:
     ```bash
     kubectl logs -n robot-shop deployment/<service-name> --tail=100
     ```
  2. Search logs via Loki/Fluent Bit:
     ```logql
     {namespace="robot-shop", service="<service-name>"} |= "error"
     ```
* **Remediation**:
  - If the service is attempting to connect to a restarting backing store, observe reconnect backoff.
  - Scale out replicas if CPU is throttling:
    ```bash
    kubectl scale deployment/<service-name> -n robot-shop --replicas=2
    ```

---

### 3.3 Alert: `ContainerRestartSpike`
* **Severity**: `warning` (> 2 container restarts within 15 minutes).
* **Diagnostic Steps**:
  1. Check previous container exit codes and termination reasons:
     ```bash
     kubectl get pods -n robot-shop -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].lastState.terminated.exitCode}{"\t"}{.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}'
     ```
  2. Distinguish termination causes:
     * **Exit Code 137 (SIGKILL)**: Indicates Out-Of-Memory (OOMKilled) or Kubelet liveness probe failure timeout. Check `dmesg -T` and `kubectl describe pod`.
     * **Exit Code 1 / 2**: Application unhandled exception or failed startup initialization. Check `kubectl logs --previous`.
* **Remediation**:
  - If OOMKilled, increase memory requests and limits in the deployment manifest.
  - If liveness probe timed out due to high system load, increase probe `timeoutSeconds` (e.g. from 5s to 15s) and `failureThreshold` (from 3 to 8).

---

### 3.4 Alert: `DatastoreUnavailable`
* **Severity**: `critical` (MySQL, Redis, MongoDB, or RabbitMQ unavailable).
* **Diagnostic Steps**:
  1. Check PVC mounting and volume status:
     ```bash
     kubectl get pvc -n robot-shop
     kubectl describe pvc -n robot-shop
     ```
  2. Inspect MySQL database integrity:
     ```bash
     kubectl logs -n robot-shop deployment/mysql --tail=50
     ```
  3. Verify database tables exist:
     ```bash
     kubectl exec -n robot-shop deployment/mysql -- mysql -uroot -probotshop -e "SHOW DATABASES; USE cities; SHOW TABLES;"
     ```
* **Remediation**:
  - **CRITICAL SAFEGUARD**: Never delete PVCs or run destructive disk repair.
  - If MySQL storage reports corruption or lock errors, verify whether an existing InnoDB transaction log lock exists (`ibdata1`).
  - If data loss has occurred, restore immediately from verified recovery backups:
    - Backups located at: `backups/recovery_20261104_184021/`
    - Manifest reference: [`RECOVERY_BACKUP_MANIFEST.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/RECOVERY_BACKUP_MANIFEST.md)
    ```bash
    kubectl exec -i -n robot-shop deployment/mysql -- mysql -uroot -probotshop cities < backups/recovery_20261104_184021/mysql_cities_database.sql
    ```

---

### 3.5 Operational Failure Mode: Control Plane Probe Starvation & Exit Code 137
* **Context**: Discovered during the WSL2 filesystem interruption and high-load recovery incident.
* **Mechanism**: When host or WSL2 CPU spikes (>1,000% load across cores), Kubelet's `/livez` probe against `kube-apiserver` times out (15s deadline exceeded 8 times). Kubelet issues SIGKILL (`exitCode: 137`) to the container.
* **Diagnostic Command**:
  ```bash
  docker exec capstone-cluster-control-plane crictl inspect <container-id> | grep -i -E 'exitCode|reason'
  ```
* **Remediation**:
  1. **Do not panic restart the cluster or kill etcd.**
  2. Pause heavy background tasks, test loops, or load generators to allow CPU load to drop below 4.0.
  3. Allow containerd to finish static pod container restart; the API server will self-heal within 60–90 seconds once CPU contention normalizes.

---

### 3.6 Operational Failure Mode: Stale Socket Pool in Node.js Services
* **Context**: Node.js microservices (e.g. `catalogue`) maintain a connection pool to MongoDB/Redis. If the datastore briefly restarts or drops connections during a cluster disruption, older Node.js drivers may retain dead sockets, returning connection errors (`MongoError`).
* **Diagnostic Command**:
  ```bash
  kubectl logs -n robot-shop deployment/catalogue --tail=30 | grep -i "MongoError"
  ```
* **Remediation**:
  - Under normal operations, perform a rolling restart to refresh the connection pool without downtime:
    ```bash
    kubectl rollout restart deployment/catalogue -n robot-shop
    ```
  - *Note*: If under strict freeze or assessment safeguards prohibiting workload modification, document the condition and monitor recovery.

---

## 4. Emergency Contacts & Escalation Matrix

| Role | Responder | Primary Channel | Escalation Target |
| :--- | :--- | :--- | :--- |
| **Primary SRE On-Call** | DevOps Capstone Team | Slack `#devops-alerts` | 15-minute response SLA |
| **Secondary SRE On-Call** | TS Academy Mentor | Slack `#mentors-emergency` | 30-minute response SLA |
| **Database Administrator** | Data Platform Lead | Slack `#data-reliability` | 1-hour response SLA |

