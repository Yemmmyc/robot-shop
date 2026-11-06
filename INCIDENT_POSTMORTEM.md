# Blameless Incident Postmortem
## Capstone Control Plane API Server Restarts & Filesystem Interruption Recovery
**Project**: Stan's Robot Shop (DevOps Capstone 2)  
**Cluster**: `capstone-cluster` (Local Kind Cluster on WSL2 Ubuntu-22.04)  
**Date of Incident**: 2026-11-04 to 2026-11-05  
**Severity**: SEV-1 (Critical Infrastructure Degradation)  
**Status**: Resolved — All Workloads 100% Operational & Verified  
**Lead Investigators**: DevOps Engineering & SRE Team  

---

## 1. Executive Summary

Between 16:30 UTC on 4 November 2026 and 09:30 UTC on 5 November 2026, the local Kubernetes cluster `capstone-cluster` experienced repeated `kube-apiserver` restarts (141 cumulative restarts) following a Windows Subsystem for Linux (WSL2) filesystem interruption and host sleep event. During peak contention, `kubectl` commands intermittently failed with connection resets and TLS handshake timeouts, and the Kubelet logged repeated probe failures and lease renewal errors.

Rather than deleting or recreating the cluster, the engineering team executed a disciplined, read-only root-cause investigation, established cryptographic recovery backups of etcd and MySQL, and isolated the failure mechanism: **Kubelet liveness probe starvation caused by extreme CPU contention (>1,400% CPU, load average >80) tripping the 15-second `/livez` timeout, resulting in Kubelet issuing SIGKILL (`exitCode: 137`) to the API server container.**

Zero data loss occurred. All 12 Robot Shop microservices and all 5 Capstone 1 (`example-voting-app`) workloads remained intact, the cluster self-healed once resource contention subsided, and all 13 automated smoke tests passed with 100% success.

---

## 2. Impact Assessment

| Dimension | Impact Level | Description |
| :--- | :--- | :--- |
| **Data Integrity** | **Zero Data Loss (0%)** | MySQL `cities` and `ratings` databases 100% intact. MongoDB documents 100% intact. Cryptographically verified backups secured. |
| **Control Plane Availability** | **Intermittent Degradation** | `kube-apiserver` restarted 141 times over 18 hours. API calls intermittently failed during 60–90 second reboot windows. |
| **Workload Availability** | **Preserved (Containerd)** | Existing running application containers in `robot-shop` and `capstone` namespaces continued executing during API server restarts. |
| **Capstone 1 Co-Tenancy** | **Zero Impact** | Capstone 1 (`example-voting-app`) pods (`db`, `redis`, `result`, `vote`, `worker`) remained 1/1 Running throughout. |

---

## 3. Timeline of Events (All times in UTC)

| Timestamp | Phase | Event Description |
| :--- | :--- | :--- |
| **2026-11-04 16:30** | *Trigger* | Host machine enters sleep cycle; WSL2 virtual disk encounters filesystem interruption and suspension. |
| **2026-11-04 17:15** | *Detection* | User resumes environment. `kubectl get nodes` intermittently fails with connection resets. Kubelet logs show API server connection refusals. |
| **2026-11-04 17:45** | *Triage* | Strict non-destructive safeguards enforced: No `kind delete cluster`, no kubeadm reset, no pod deletion, no volume pruning. |
| **2026-11-04 18:00** | *Diagnosis* | Certificates inspected: valid through October 2027 (not expired). etcd container inspected: healthy and operational. Static pod manifests intact. |
| **2026-11-04 18:33** | *Assessment* | Read-only assessment completed and published as [`KUBERNETES_RECOVERY_ASSESSMENT.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/KUBERNETES_RECOVERY_ASSESSMENT.md). |
| **2026-11-04 18:40** | *Containment* | Cryptographic recovery backups taken outside container storage: etcd snapshot (`15.14 MB`) and MySQL database dumps (`cities`: 40.58 KB, `ratings`: 1.76 KB). Verified via SHA-256 and published as [`RECOVERY_BACKUP_MANIFEST.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/RECOVERY_BACKUP_MANIFEST.md). |
| **2026-11-04 21:01** | *Observability* | Non-invasive monitoring tool created ([`scripts/robot_shop_monitor.py`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/scripts/robot_shop_monitor.py)). Baselined health published in [`PHASE_D_OBSERVABILITY_REPORT.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/PHASE_D_OBSERVABILITY_REPORT.md). |
| **2026-11-05 02:09** | *Verification* | Automated test suite implemented ([`scripts/robot_shop_test_suite.py`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/scripts/robot_shop_test_suite.py)). All 13 smoke tests pass. Results published in [`PHASE_E_TEST_REPORT.md`](file:///wsl.localhost/Ubuntu-22.04/home/yemmm/projects/robot-shop/PHASE_E_TEST_REPORT.md). |
| **2026-11-05 09:07** | *Root Cause* | Container inspect (`crictl inspect de614545f102d`) confirms `exitCode: 137` (SIGKILL). Kubelet event log confirms 8 consecutive `/livez` probe timeouts caused by CPU starvation. |
| **2026-11-05 09:24** | *Resolution* | CPU load stabilizes below 2.0; API server reaches steady state. All 12 Robot Shop pods and 5 Capstone 1 pods confirmed 1/1 Running. Cluster node declared `Ready`. |

---

## 4. Root Cause Analysis (5 Whys Methodology)

1. **Why did `kubectl` fail with connection resets?**  
   The `kube-apiserver` process was repeatedly killed and restarted, dropping active TLS connections during its initialization window.

2. **Why was `kube-apiserver` killed?**  
   The Kubelet issued a `SIGKILL` (`exitCode: 137`) because the static pod's liveness probe (`/livez`) failed 8 consecutive times.

3. **Why did the `/livez` probe fail 8 consecutive times?**  
   Each probe request timed out after 15 seconds because the API server process was starved of CPU time and could not respond within the deadline.

4. **Why was the API server starved of CPU time?**  
   The single Kind control-plane node experienced massive CPU contention (load average >80, container CPU utilization >1,400%), driven by concurrent container reconnect storms, containerd status syncs, and bursts of unthrottled diagnostic commands immediately after the VM resumed.

5. **Why did the system resume under heavy backlog load?**  
   The underlying Windows host suspended WSL2 during a sleep cycle without gracefully draining or pausing container timers, leaving all background polling loops to fire simultaneously upon wake.

---

## 5. Lessons Learned

### What Went Well
* **Strict Non-Destructive Discipline**: Resisting the temptation to delete the Kind cluster or prune Docker volumes preserved all persistent databases and averted catastrophic data loss.
* **Cryptographic Verification**: Backing up etcd and MySQL databases and confirming SHA-256 hashes provided an absolute safety net before any subsequent operations.
* **Containerd Process Isolation**: Even while the Kubernetes API server was restarting, containerd maintained the underlying application containers in a running state, preventing database corruption.
* **Automated Evidence**: The creation of standard-library Python monitors and test suites allowed deep verification without introducing third-party dependencies or additional cluster load.

### What Went Poorly
* **Aggressive Probe Thresholds on Constrained Nodes**: The default kubeadm liveness probe timeout (15s) and failure threshold (8) are calibrated for production bare-metal clusters, not single-node nested Kind clusters under virtualization.
* **Lack of Resource Reservations**: The control plane containers lacked guaranteed CPU reservations (`system-reserved` / `kube-reserved`), allowing user-space workloads to starve the apiserver.
* **Persistent Socket State in Node.js Services**: The `catalogue` service retained stale MongoDB socket references from before the interruption, requiring rolling restart awareness in the runbook.

---

## 6. Action Items & Remediation Matrix

| Action Item | Type | Owner | Priority | Target Status |
| :--- | :--- | :--- | :--- | :--- |
| Create cryptographic recovery backups of etcd and MySQL | Mitigate | DevOps Lead | P0 | **COMPLETED** (`RECOVERY_BACKUP_MANIFEST.md`) |
| Establish non-invasive monitoring & alerting script | Detect | SRE Lead | P0 | **COMPLETED** (`scripts/robot_shop_monitor.py`) |
| Document SRE operational triage and recovery runbook | Prevent | DevOps Lead | P0 | **COMPLETED** (`RUNBOOK.md`) |
| Define formal SLOs, 30-day error budget, and burn rates | Policy | SRE Lead | P0 | **COMPLETED** (`SLO.md`) |
| Package PrometheusRule, Alertmanager, Fluent Bit, Loki, OTel | Code | SRE Lead | P1 | **COMPLETED** (`observability/`) |
| Tune Kubelet static pod liveness probe timeouts for Kind | Tune | Infra Team | P2 | Planned for next cluster maintenance |
| Add auto-reconnect logic to Node.js MongoDB driver | Prevent | App Team | P2 | Backlog ticket RS-104 |

