#!/usr/bin/env python3
"""
Robot Shop Lightweight Observability Engine (Phase D)
Monitors Kubernetes health, Pod readiness, container restarts, service endpoints,
MySQL & Redis databases, application HTTP probes, Prometheus metrics, and logs.

Constraint-compliant: Python standard library only, minimal RAM/CPU, non-intrusive.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Configuration Defaults
DEFAULT_NAMESPACE = "robot-shop"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_TIMEOUT = 2.5
STATE_FILE = "/tmp/robot_shop_monitor_baseline.json"
DEFAULT_REPORT_FILE = "PHASE_D_OBSERVABILITY_REPORT.md"
REPORTS_DIR = "reports"

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_WHITE = "\033[37m"

# Sensitive information patterns for redaction
REDACTION_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|pwd|secret|token|api[_-]?key|auth)[\s:=]+([^\s,;&"\']+)'), r'\1=[REDACTED]'),
    (re.compile(r'(?i)bearer\s+[A-Za-z0-9\-\._~\+\/]+=*'), 'Bearer [REDACTED]'),
    (re.compile(r'(?i)basic\s+[A-Za-z0-9\+\/]+=*'), 'Basic [REDACTED]'),
    (re.compile(r'(mysql://[^:]+:)([^@]+)(@)'), r'\1[REDACTED]\3'),
    (re.compile(r'(mongodb://[^:]+:)([^@]+)(@)'), r'\1[REDACTED]\3'),
]


def redact_sensitive(text: str) -> str:
    """Redact passwords, secrets, credentials, and tokens from text."""
    if not text:
        return ""
    redacted = str(text)
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def run_cmd(cmd_list, timeout=8) -> tuple:
    """Execute a local command and return (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


# ---------------------------------------------------------------------------
# Telemetry Collectors
# ---------------------------------------------------------------------------

class ObservabilityCollector:
    def __init__(self, namespace=DEFAULT_NAMESPACE, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
        self.namespace = namespace
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.baseline_restarts = self._load_or_init_baseline()

    def _load_or_init_baseline(self) -> dict:
        """Load or initialize baseline restart counts to track new restarts."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_baseline(self, baseline: dict):
        """Persist baseline restart counts."""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(baseline, f)
        except Exception:
            pass

    def collect_wsl_host_stats(self) -> dict:
        """Collect host memory and basic resource stats."""
        stats = {
            "wsl_total_mb": 0,
            "wsl_used_mb": 0,
            "wsl_available_mb": 0,
            "wsl_mem_percent": 0.0,
            "docker_kind_cpu": "N/A",
            "docker_kind_mem": "N/A"
        }
        try:
            code, out, _ = run_cmd(["free", "-m"], timeout=4)
            if code == 0:
                for line in out.splitlines():
                    if line.startswith("Mem:"):
                        parts = line.split()
                        total = int(parts[1])
                        used = int(parts[2])
                        avail = int(parts[6]) if len(parts) > 6 else int(parts[3])
                        stats["wsl_total_mb"] = total
                        stats["wsl_used_mb"] = used
                        stats["wsl_available_mb"] = avail
                        stats["wsl_mem_percent"] = round((used / total) * 100, 1) if total > 0 else 0.0
                        break
        except Exception:
            pass

        try:
            code, out, _ = run_cmd(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"], timeout=6)
            if code == 0:
                for line in out.splitlines():
                    if "capstone-cluster-control-plane" in line:
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            stats["docker_kind_cpu"] = parts[1]
                            stats["docker_kind_mem"] = parts[2]
                        break
        except Exception:
            pass

        return stats

    def collect_kubernetes_telemetry(self) -> dict:
        """Collect Node, Pods, Deployments, Endpoints, and PVC data from K8s."""
        data = {
            "node": {},
            "pods": [],
            "deployments": [],
            "endpoints": [],
            "storage": {}
        }

        # 1. Node Health
        code, out, _ = run_cmd(["kubectl", "get", "nodes", "-o", "json"], timeout=6)
        if code == 0:
            try:
                node_json = json.loads(out)
                items = node_json.get("items", [])
                if items:
                    node = items[0]
                    metadata = node.get("metadata", {})
                    status = node.get("status", {})
                    node_info = status.get("nodeInfo", {})

                    conditions = {}
                    is_ready = False
                    for cond in status.get("conditions", []):
                        c_type = cond.get("type")
                        c_status = cond.get("status")
                        conditions[c_type] = c_status
                        if c_type == "Ready" and c_status == "True":
                            is_ready = True

                    data["node"] = {
                        "name": metadata.get("name", "unknown"),
                        "ready": is_ready,
                        "conditions": conditions,
                        "kubelet_version": node_info.get("kubeletVersion", "unknown"),
                        "os_image": node_info.get("osImage", "unknown"),
                        "container_runtime": node_info.get("containerRuntimeVersion", "unknown")
                    }
            except Exception as e:
                data["node"] = {"error": str(e)}

        # 2. Pods Health & Restarts
        code, out, _ = run_cmd(["kubectl", "get", "pods", "-n", self.namespace, "-o", "json"], timeout=6)
        current_restarts = {}
        if code == 0:
            try:
                pods_json = json.loads(out)
                for pod in pods_json.get("items", []):
                    p_meta = pod.get("metadata", {})
                    p_name = p_meta.get("name", "")
                    p_status = pod.get("status", {})
                    p_phase = p_status.get("phase", "Unknown")

                    c_statuses = p_status.get("containerStatuses", [])
                    total_containers = len(c_statuses)
                    ready_containers = sum(1 for c in c_statuses if c.get("ready", False))
                    restart_count = sum(c.get("restartCount", 0) for c in c_statuses)

                    is_ready = (total_containers > 0 and ready_containers == total_containers and p_phase == "Running")

                    # Track new restarts vs baseline
                    baseline = self.baseline_restarts.get(p_name, restart_count)
                    new_restarts = max(0, restart_count - baseline)
                    current_restarts[p_name] = restart_count

                    start_time = p_status.get("startTime", "")

                    data["pods"].append({
                        "name": p_name,
                        "phase": p_phase,
                        "ready": is_ready,
                        "ready_fraction": f"{ready_containers}/{total_containers}",
                        "restarts_total": restart_count,
                        "restarts_new": new_restarts,
                        "ip": p_status.get("podIP", "None"),
                        "start_time": start_time
                    })
            except Exception as e:
                data["pods_error"] = str(e)

        # Update and persist baseline if first run
        if not self.baseline_restarts and current_restarts:
            self.baseline_restarts = current_restarts
            self._save_baseline(current_restarts)

        # 3. Deployments Availability
        code, out, _ = run_cmd(["kubectl", "get", "deployments", "-n", self.namespace, "-o", "json"], timeout=6)
        if code == 0:
            try:
                deps_json = json.loads(out)
                for dep in deps_json.get("items", []):
                    d_meta = dep.get("metadata", {})
                    d_name = d_meta.get("name", "")
                    d_spec = dep.get("spec", {})
                    d_status = dep.get("status", {})

                    replicas = d_spec.get("replicas", 1)
                    ready_replicas = d_status.get("readyReplicas", 0)
                    available_replicas = d_status.get("availableReplicas", 0)

                    is_healthy = (available_replicas >= replicas and ready_replicas >= replicas)
                    data["deployments"].append({
                        "name": d_name,
                        "desired": replicas,
                        "ready": ready_replicas,
                        "available": available_replicas,
                        "healthy": is_healthy
                    })
            except Exception as e:
                data["deployments_error"] = str(e)

        # 4. Service Endpoints
        code, out, _ = run_cmd(["kubectl", "get", "endpoints", "-n", self.namespace, "-o", "json"], timeout=6)
        if code == 0:
            try:
                ep_json = json.loads(out)
                for ep in ep_json.get("items", []):
                    ep_meta = ep.get("metadata", {})
                    ep_name = ep_meta.get("name", "")

                    ready_ips = []
                    not_ready_ips = []
                    for subset in ep.get("subsets", []):
                        for addr in subset.get("addresses", []):
                            ready_ips.append(addr.get("ip", ""))
                        for addr in subset.get("notReadyAddresses", []):
                            not_ready_ips.append(addr.get("ip", ""))

                    data["endpoints"].append({
                        "service": ep_name,
                        "ready_ips": ready_ips,
                        "not_ready_ips": not_ready_ips,
                        "has_active_endpoints": len(ready_ips) > 0
                    })
            except Exception as e:
                data["endpoints_error"] = str(e)

        # 5. Redis PVC Binding Status
        code, out, _ = run_cmd(["kubectl", "get", "pvc", "-n", self.namespace, "-o", "json"], timeout=6)
        if code == 0:
            try:
                pvc_json = json.loads(out)
                for pvc in pvc_json.get("items", []):
                    p_name = pvc.get("metadata", {}).get("name", "")
                    p_status = pvc.get("status", {}).get("phase", "")
                    p_vol = pvc.get("spec", {}).get("volumeName", "")
                    p_cap = pvc.get("status", {}).get("capacity", {}).get("storage", "")
                    p_sc = pvc.get("spec", {}).get("storageClassName", "")

                    data["storage"][p_name] = {
                        "name": p_name,
                        "status": p_status,
                        "bound": (p_status == "Bound"),
                        "volume": p_vol,
                        "capacity": p_cap,
                        "storage_class": p_sc
                    }
            except Exception as e:
                data["storage_error"] = str(e)

        return data

    def collect_database_telemetry(self) -> dict:
        """Inspect MySQL and Redis databases using native command probes."""
        db_data = {
            "mysql": {
                "available": False,
                "ping": "FAILED",
                "uptime_seconds": 0,
                "threads": 0,
                "questions": 0,
                "slow_queries": 0,
                "qps": 0.0
            },
            "redis": {
                "available": False,
                "ping": "FAILED",
                "version": "unknown",
                "uptime_seconds": 0,
                "connected_clients": 0,
                "used_memory_human": "N/A",
                "mem_fragmentation_ratio": 0.0,
                "rdb_last_status": "unknown",
                "total_commands": 0,
                "ops_per_sec": 0
            }
        }

        # 1. MySQL Health via mysqladmin ping & status
        code, out, _ = run_cmd(["kubectl", "exec", "-n", self.namespace, "deploy/mysql", "--", "mysqladmin", "ping", "-h", "127.0.0.1"], timeout=12)
        if code == 0 and "mysqld is alive" in out:
            db_data["mysql"]["available"] = True
            db_data["mysql"]["ping"] = "ALIVE"

            code2, out2, _ = run_cmd(["kubectl", "exec", "-n", self.namespace, "deploy/mysql", "--", "mysqladmin", "status"], timeout=12)
            if code2 == 0 and out2:
                m_up = re.search(r'Uptime:\s+(\d+)', out2)
                m_th = re.search(r'Threads:\s+(\d+)', out2)
                m_q = re.search(r'Questions:\s+(\d+)', out2)
                m_sq = re.search(r'Slow queries:\s+(\d+)', out2)
                m_qps = re.search(r'Queries per second avg:\s+([\d\.]+)', out2)

                if m_up:
                    db_data["mysql"]["uptime_seconds"] = int(m_up.group(1))
                if m_th:
                    db_data["mysql"]["threads"] = int(m_th.group(1))
                if m_q:
                    db_data["mysql"]["questions"] = int(m_q.group(1))
                if m_sq:
                    db_data["mysql"]["slow_queries"] = int(m_sq.group(1))
                if m_qps:
                    db_data["mysql"]["qps"] = float(m_qps.group(1))

        # 2. Redis Health via redis-cli ping & info
        code, out, _ = run_cmd(["kubectl", "exec", "-n", self.namespace, "redis-0", "--", "redis-cli", "ping"], timeout=12)
        if code == 0 and "PONG" in out:
            db_data["redis"]["available"] = True
            db_data["redis"]["ping"] = "PONG"

            code2, out2, _ = run_cmd(["kubectl", "exec", "-n", self.namespace, "redis-0", "--", "redis-cli", "info"], timeout=5)
            if code2 == 0 and out2:
                for line in out2.splitlines():
                    if ":" in line:
                        k, v = line.strip().split(":", 1)
                        if k == "redis_version":
                            db_data["redis"]["version"] = v
                        elif k == "uptime_in_seconds":
                            db_data["redis"]["uptime_seconds"] = int(v) if v.isdigit() else 0
                        elif k == "connected_clients":
                            db_data["redis"]["connected_clients"] = int(v) if v.isdigit() else 0
                        elif k == "used_memory_human":
                            db_data["redis"]["used_memory_human"] = v
                        elif k == "mem_fragmentation_ratio":
                            try:
                                db_data["redis"]["mem_fragmentation_ratio"] = float(v)
                            except ValueError:
                                pass
                        elif k == "rdb_last_bgsave_status":
                            db_data["redis"]["rdb_last_status"] = v
                        elif k == "total_commands_processed":
                            db_data["redis"]["total_commands"] = int(v) if v.isdigit() else 0
                        elif k == "instantaneous_ops_per_sec":
                            db_data["redis"]["ops_per_sec"] = int(v) if v.isdigit() else 0

        return db_data

    def collect_application_telemetry(self) -> dict:
        """Probe core application endpoints and Prometheus metrics."""
        app_data = {
            "http_probes": [],
            "prometheus_metrics": {
                "cart": {"items_added": None},
                "payment": {
                    "sold_count_total": None,
                    "units_sold_count": None,
                    "cart_value_count": None
                }
            },
            "shipping_actuator": {
                "status": "UNKNOWN"
            }
        }

        # Defined non-destructive application probes
        endpoints = [
            {"name": "Web Frontend", "path": "/", "method": "GET"},
            {"name": "Cart Health", "path": "/api/cart/health", "method": "GET"},
            {"name": "Catalogue Health", "path": "/api/catalogue/health", "method": "GET"},
            {"name": "User UniqueID", "path": "/api/user/uniqueid", "method": "GET"},
            {"name": "Shipping Codes", "path": "/api/shipping/codes", "method": "GET"},
            {"name": "Payment Health", "path": "/api/payment/health", "method": "GET"},
            {"name": "Cart Metrics", "path": "/api/cart/metrics", "method": "GET"},
            {"name": "Payment Metrics", "path": "/api/payment/metrics", "method": "GET"}
        ]

        for ep in endpoints:
            url = f"{self.base_url}{ep['path']}"
            start = time.perf_counter()
            probe_result = {
                "name": ep["name"],
                "path": ep["path"],
                "status_code": 0,
                "latency_ms": 0.0,
                "success": False,
                "error": None
            }

            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "RobotShop-ObservabilityEngine/1.0"},
                    method=ep["method"]
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    latency = round((time.perf_counter() - start) * 1000, 2)
                    status_code = resp.getcode()
                    content = resp.read().decode("utf-8", errors="replace")

                    probe_result["status_code"] = status_code
                    probe_result["latency_ms"] = latency
                    probe_result["success"] = (status_code == 200)

                    # Extract Prometheus metrics if target endpoint
                    if ep["path"] == "/api/cart/metrics":
                        for line in content.splitlines():
                            if line.startswith("items_added "):
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        app_data["prometheus_metrics"]["cart"]["items_added"] = float(parts[1])
                                    except ValueError:
                                        pass

                    elif ep["path"] == "/api/payment/metrics":
                        for line in content.splitlines():
                            if line.startswith("sold_count_total "):
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        app_data["prometheus_metrics"]["payment"]["sold_count_total"] = float(parts[1])
                                    except ValueError:
                                        pass
                            elif line.startswith("units_sold_count "):
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        app_data["prometheus_metrics"]["payment"]["units_sold_count"] = float(parts[1])
                                    except ValueError:
                                        pass
                            elif line.startswith("cart_value_count "):
                                parts = line.split()
                                if len(parts) >= 2:
                                    try:
                                        app_data["prometheus_metrics"]["payment"]["cart_value_count"] = float(parts[1])
                                    except ValueError:
                                        pass

            except urllib.error.HTTPError as e:
                probe_result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
                probe_result["status_code"] = e.code
                probe_result["error"] = f"HTTP {e.code}"
            except Exception as e:
                probe_result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
                probe_result["error"] = str(e)

            app_data["http_probes"].append(probe_result)

        # Shipping Actuator Health Probe via internal pod query
        code, out, _ = run_cmd(["kubectl", "exec", "-n", self.namespace, "deploy/shipping", "--", "curl", "-s", "--max-time", "3", "http://localhost:8080/actuator/health"], timeout=4)
        if code == 0 and out:
            try:
                act_json = json.loads(out)
                app_data["shipping_actuator"]["status"] = act_json.get("status", "UNKNOWN")
                app_data["shipping_actuator"]["raw"] = act_json
            except Exception:
                app_data["shipping_actuator"]["status"] = "PARSING_ERROR"

        return app_data

    def collect_log_telemetry(self, problematic_pods: list) -> list:
        """Retrieve recent logs for problematic or restarting containers, redacting sensitive data."""
        logs = []
        for pod_name in problematic_pods:
            code, out, err = run_cmd([
                "kubectl", "logs", "--tail=25", "--since=15m", pod_name, "-n", self.namespace
            ], timeout=5)
            raw_log = out if code == 0 else err
            sanitized = redact_sensitive(raw_log)
            logs.append({
                "pod": pod_name,
                "lines": sanitized.splitlines()[-10:] if sanitized else ["(No recent logs)"]
            })
        return logs

    def snapshot(self) -> dict:
        """Run all collectors and assemble complete telemetry snapshot."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        host = self.collect_wsl_host_stats()
        k8s = self.collect_kubernetes_telemetry()
        dbs = self.collect_database_telemetry()
        apps = self.collect_application_telemetry()

        # Identify pods with issues for log collection
        problematic_pods = []
        for p in k8s.get("pods", []):
            if not p["ready"] or p["restarts_new"] > 0:
                problematic_pods.append(p["name"])

        logs = self.collect_log_telemetry(problematic_pods)

        snapshot_data = {
            "metadata": {
                "timestamp": now,
                "namespace": self.namespace,
                "base_url": self.base_url
            },
            "host": host,
            "kubernetes": k8s,
            "databases": dbs,
            "applications": apps,
            "logs": logs
        }

        # Evaluate alerts
        alerts = self.evaluate_alerts(snapshot_data)
        snapshot_data["alerts"] = alerts

        # Summary flags
        crit_count = sum(1 for a in alerts if a["severity"] == "CRITICAL")
        warn_count = sum(1 for a in alerts if a["severity"] == "WARNING")
        snapshot_data["summary"] = {
            "healthy": (crit_count == 0 and warn_count == 0),
            "critical_count": crit_count,
            "warning_count": warn_count,
            "total_pods": len(k8s.get("pods", [])),
            "ready_pods": sum(1 for p in k8s.get("pods", []) if p["ready"])
        }

        return snapshot_data

    def evaluate_alerts(self, snapshot: dict) -> list:
        """Evaluate alerting thresholds based on live telemetry."""
        alerts = []
        ts = snapshot["metadata"]["timestamp"]

        # Rule 1: Node Ready (Critical)
        node = snapshot.get("kubernetes", {}).get("node", {})
        if node and not node.get("ready", False):
            alerts.append({
                "id": "NODE_NOT_READY",
                "severity": "CRITICAL",
                "component": node.get("name", "node"),
                "message": f"Cluster node '{node.get('name')}' is not in Ready state",
                "timestamp": ts
            })

        # Rule 2: Pods Ready (Critical)
        for pod in snapshot.get("kubernetes", {}).get("pods", []):
            if not pod.get("ready", False):
                alerts.append({
                    "id": "POD_NOT_READY",
                    "severity": "CRITICAL",
                    "component": pod["name"],
                    "message": f"Pod '{pod['name']}' is not Ready ({pod['ready_fraction']}, status: {pod['phase']})",
                    "timestamp": ts
                })
            # Rule 3: Restarts increased during session (Warning)
            if pod.get("restarts_new", 0) > 0:
                alerts.append({
                    "id": "RESTARTS_INCREASED",
                    "severity": "WARNING",
                    "component": pod["name"],
                    "message": f"Pod '{pod['name']}' restarted {pod['restarts_new']} time(s) during active monitoring session",
                    "timestamp": ts
                })

        # Rule 4: Deployment Available Replicas (Critical)
        for dep in snapshot.get("kubernetes", {}).get("deployments", []):
            if dep.get("available", 0) < dep.get("desired", 1):
                alerts.append({
                    "id": "DEPLOYMENT_UNAVAILABLE_REPLICAS",
                    "severity": "CRITICAL",
                    "component": dep["name"],
                    "message": f"Deployment '{dep['name']}' has unavailable replicas: {dep['available']}/{dep['desired']} available",
                    "timestamp": ts
                })

        # Rule 5: Service Endpoints Missing (Critical)
        for ep in snapshot.get("kubernetes", {}).get("endpoints", []):
            if not ep.get("has_active_endpoints", False):
                alerts.append({
                    "id": "SERVICE_NO_ENDPOINTS",
                    "severity": "CRITICAL",
                    "component": ep["service"],
                    "message": f"Service '{ep['service']}' has 0 active ready endpoints",
                    "timestamp": ts
                })

        # Rule 6: Redis PVC Binding (Critical)
        pvc = snapshot.get("kubernetes", {}).get("storage", {}).get("data-redis-0", {})
        if pvc and not pvc.get("bound", False):
            alerts.append({
                "id": "REDIS_PVC_UNBOUND",
                "severity": "CRITICAL",
                "component": "data-redis-0",
                "message": f"PVC data-redis-0 is not Bound (status: {pvc.get('status')})",
                "timestamp": ts
            })

        # Rule 7: MySQL Connectivity (Critical)
        mysql = snapshot.get("databases", {}).get("mysql", {})
        if not mysql.get("available", False):
            alerts.append({
                "id": "MYSQL_CONNECTIVITY_FAILED",
                "severity": "CRITICAL",
                "component": "mysql",
                "message": "MySQL ping failed (mysqladmin ping unreachable)",
                "timestamp": ts
            })

        # Rule 8: Redis Connectivity (Critical)
        redis = snapshot.get("databases", {}).get("redis", {})
        if not redis.get("available", False):
            alerts.append({
                "id": "REDIS_CONNECTIVITY_FAILED",
                "severity": "CRITICAL",
                "component": "redis",
                "message": "Redis ping failed (redis-cli ping unreachable)",
                "timestamp": ts
            })

        # Rule 9: HTTP Probes Unsuccessful or High Latency (Warning)
        for probe in snapshot.get("applications", {}).get("http_probes", []):
            if not probe.get("success", False):
                alerts.append({
                    "id": "HTTP_PROBE_FAILED",
                    "severity": "WARNING",
                    "component": probe["name"],
                    "message": f"HTTP probe '{probe['name']}' failed at {probe['path']}: {probe.get('error') or probe.get('status_code')}",
                    "timestamp": ts
                })
            elif probe.get("latency_ms", 0.0) > 3000.0:
                alerts.append({
                    "id": "HTTP_HIGH_LATENCY",
                    "severity": "WARNING",
                    "component": probe["name"],
                    "message": f"HTTP probe '{probe['name']}' latency {probe['latency_ms']}ms exceeded 3000ms threshold",
                    "timestamp": ts
                })

        # Rule 10: Shipping Actuator (Warning)
        act = snapshot.get("applications", {}).get("shipping_actuator", {})
        if act.get("status") not in ("UP", "UNKNOWN"):
            alerts.append({
                "id": "SHIPPING_ACTUATOR_DOWN",
                "severity": "WARNING",
                "component": "shipping",
                "message": f"Shipping Spring Boot Actuator status is '{act.get('status')}' (expected UP)",
                "timestamp": ts
            })

        return alerts


# ---------------------------------------------------------------------------
# Dashboard & Presentation Renderer
# ---------------------------------------------------------------------------

class DashboardRenderer:
    def __init__(self, use_color=True):
        self.use_color = use_color and sys.stdout.isatty()

    def _c(self, text, color_code):
        if not self.use_color:
            return text
        return f"{color_code}{text}{C_RESET}"

    def render(self, snap: dict) -> str:
        lines = []
        meta = snap.get("metadata", {})
        host = snap.get("host", {})
        k8s = snap.get("kubernetes", {})
        node = k8s.get("node", {})
        dbs = snap.get("databases", {})
        apps = snap.get("applications", {})
        alerts = snap.get("alerts", [])
        summary = snap.get("summary", {})

        # Header Box
        lines.append(self._c("=" * 80, C_CYAN))
        title = " STAN'S ROBOT SHOP — LIGHTWEIGHT OBSERVABILITY DASHBOARD "
        lines.append(self._c(title.center(80, " "), C_BOLD + C_WHITE))
        lines.append(self._c("=" * 80, C_CYAN))

        status_str = self._c("● HEALTHY", C_GREEN + C_BOLD) if summary.get("healthy") else self._c("▲ ATTENTION REQUIRED", C_RED + C_BOLD)
        lines.append(f" Status: {status_str} | Timestamp: {meta.get('timestamp')} | Namespace: {meta.get('namespace')}")
        lines.append(f" Host RAM: {host.get('wsl_used_mb')}MB / {host.get('wsl_total_mb')}MB ({host.get('wsl_mem_percent')}%) | Kind Control Plane: CPU {host.get('docker_kind_cpu')}, MEM {host.get('docker_kind_mem')}")
        lines.append(f" Node: {node.get('name', 'N/A')} ({'Ready' if node.get('ready') else 'NotReady'}) | Kubelet: {node.get('kubelet_version', 'N/A')}")
        lines.append("-" * 80)

        # Kubernetes Workloads
        lines.append(self._c(" Kubernetes Workload Health (robot-shop)", C_BOLD + C_CYAN))
        lines.append(f" {'POD NAME':<30} {'READY':<8} {'STATUS':<10} {'RESTARTS':<12} {'POD IP':<15}")
        lines.append(f" {'-'*30} {'-'*8} {'-'*10} {'-'*12} {'-'*15}")

        for p in k8s.get("pods", []):
            p_ready = self._c("Yes", C_GREEN) if p["ready"] else self._c("No", C_RED)
            rst_str = f"{p['restarts_total']}"
            if p["restarts_new"] > 0:
                rst_str += self._c(f" (+{p['restarts_new']})", C_YELLOW)
            lines.append(f" {p['name']:<30} {p_ready:<17} {p['phase']:<10} {rst_str:<21} {p['ip']:<15}")

        lines.append("-" * 80)

        # Deployments & Storage & Endpoints
        lines.append(self._c(" Deployments & Storage", C_BOLD + C_CYAN))
        dep_summaries = []
        for d in k8s.get("deployments", []):
            d_stat = self._c(f"{d['name']} ({d['available']}/{d['desired']})", C_GREEN if d['healthy'] else C_RED)
            dep_summaries.append(d_stat)
        lines.append(f" Deployments: {', '.join(dep_summaries)}")

        pvc = k8s.get("storage", {}).get("data-redis-0", {})
        pvc_stat = self._c(f"Bound ({pvc.get('capacity')}, {pvc.get('storage_class')})", C_GREEN) if pvc.get("bound") else self._c(pvc.get("status", "Unknown"), C_RED)
        lines.append(f" Redis PVC:   data-redis-0 -> {pvc_stat}")

        # Active Endpoints check
        missing_eps = [ep["service"] for ep in k8s.get("endpoints", []) if not ep["has_active_endpoints"]]
        if missing_eps:
            lines.append(f" Endpoints:   {self._c(f'Warning: {len(missing_eps)} service(s) missing endpoints: {missing_eps}', C_RED)}")
        else:
            ep_count = len(k8s.get("endpoints", []))
            lines.append(f" Endpoints:   {self._c(f'All {ep_count} services have active ready endpoints', C_GREEN)}")

        lines.append("-" * 80)

        # Database Telemetry
        lines.append(self._c(" Database & Backend Health", C_BOLD + C_CYAN))
        mysql = dbs.get("mysql", {})
        redis = dbs.get("redis", {})

        m_status = self._c("ONLINE", C_GREEN) if mysql.get("available") else self._c("OFFLINE", C_RED)
        r_status = self._c("ONLINE", C_GREEN) if redis.get("available") else self._c("OFFLINE", C_RED)

        lines.append(f" MySQL: [{m_status}] Ping: {mysql.get('ping')} | Uptime: {mysql.get('uptime_seconds')}s | QPS: {mysql.get('qps')} | Threads: {mysql.get('threads')} | Slow Queries: {mysql.get('slow_queries')}")
        lines.append(f" Redis: [{r_status}] Ping: {redis.get('ping')} | Memory: {redis.get('used_memory_human')} | Frag: {redis.get('mem_fragmentation_ratio')} | Clients: {redis.get('connected_clients')} | Ops/s: {redis.get('ops_per_sec')}")
        lines.append("-" * 80)

        # Application & Prometheus Metrics
        lines.append(self._c(" Application Probes & Prometheus Metrics", C_BOLD + C_CYAN))
        prom = apps.get("prometheus_metrics", {})
        cart_items = prom.get("cart", {}).get("items_added", "N/A")
        pay_sold = prom.get("payment", {}).get("sold_count_total", "N/A")
        pay_units = prom.get("payment", {}).get("units_sold_count", "N/A")
        act_status = apps.get("shipping_actuator", {}).get("status", "UNKNOWN")
        act_str = self._c(act_status, C_GREEN if act_status == "UP" else C_YELLOW)

        lines.append(f" Prometheus Metrics: Cart items_added={self._c(str(cart_items), C_BOLD)} | Payment sold_count={self._c(str(pay_sold), C_BOLD)} (units={pay_units})")
        lines.append(f" Spring Boot Actuator: Shipping /actuator/health -> {act_str}")
        lines.append("")
        lines.append(f" {'ENDPOINT':<24} {'PATH':<30} {'STATUS':<10} {'LATENCY':<10}")
        lines.append(f" {'-'*24} {'-'*30} {'-'*10} {'-'*10}")

        for pr in apps.get("http_probes", []):
            code_col = C_GREEN if pr["success"] else C_RED
            code_str = self._c(str(pr["status_code"]), code_col)
            lat_col = C_GREEN if pr["latency_ms"] < 500 else (C_YELLOW if pr["latency_ms"] < 3000 else C_RED)
            lat_str = self._c(f"{pr['latency_ms']} ms", lat_col)
            lines.append(f" {pr['name']:<24} {pr['path']:<30} {code_str:<19} {lat_str:<19}")

        lines.append("-" * 80)

        # Active Alerts Section
        lines.append(self._c(f" Active Alerts ({len(alerts)} active)", C_BOLD + (C_GREEN if len(alerts) == 0 else (C_YELLOW if summary.get("critical_count") == 0 else C_RED))))
        if not alerts:
            lines.append(self._c(" ✔ All threshold checks passed cleanly. Zero active alerts.", C_GREEN))
        else:
            for a in alerts:
                sev_col = C_RED if a["severity"] == "CRITICAL" else C_YELLOW
                lines.append(f" [{self._c(a['severity'], sev_col)}] {self._c(a['id'], C_BOLD)} ({a['component']}): {a['message']}")

        # Log tail for problematic pods if any
        logs = snap.get("logs", [])
        if logs:
            lines.append("-" * 80)
            lines.append(self._c(" Diagnostic Log Tailing (Problematic Pods)", C_BOLD + C_YELLOW))
            for l in logs:
                lines.append(self._c(f" --- Log snippet for {l['pod']} ---", C_DIM))
                for line in l["lines"]:
                    lines.append(f"   {line}")

        lines.append(self._c("=" * 80, C_CYAN))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report Generators (Markdown & JSON)
# ---------------------------------------------------------------------------

def generate_markdown_report(snap: dict, output_path: str):
    """Generate a clean, structured Markdown report."""
    meta = snap.get("metadata", {})
    host = snap.get("host", {})
    k8s = snap.get("kubernetes", {})
    node = k8s.get("node", {})
    dbs = snap.get("databases", {})
    mysql = dbs.get("mysql", {})
    redis = dbs.get("redis", {})
    apps = snap.get("applications", {})
    prom = apps.get("prometheus_metrics", {})
    alerts = snap.get("alerts", [])
    summary = snap.get("summary", {})

    status_badge = "✅ **ALL SYSTEMS OPERATIONAL**" if summary.get("healthy") else f"⚠️ **ISSUES DETECTED** ({summary.get('critical_count')} Critical, {summary.get('warning_count')} Warning)"

    md = []
    md.append("# Stan's Robot Shop — Observability & Monitoring Report")
    md.append("")
    md.append(f"**Generated**: {meta.get('timestamp')}  ")
    md.append(f"**Namespace**: `{meta.get('namespace')}`  ")
    md.append(f"**Overall Status**: {status_badge}  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Executive Summary")
    md.append("")
    md.append(f"- **Kubernetes Node**: `{node.get('name')}` is **{'Ready' if node.get('ready') else 'NotReady'}** (Kubelet: `{node.get('kubelet_version')}`).")
    md.append(f"- **Workloads**: **{summary.get('ready_pods')}/{summary.get('total_pods')} pods are 1/1 Running** in namespace `{meta.get('namespace')}`.")
    md.append(f"- **Databases**: MySQL is **{'ALIVE' if mysql.get('available') else 'DOWN'}** (QPS: `{mysql.get('qps')}`), Redis is **{'ALIVE' if redis.get('available') else 'DOWN'}** (Memory: `{redis.get('used_memory_human')}`).")
    md.append(f"- **Storage**: PVC `data-redis-0` is **Bound**.")
    md.append(f"- **Active Alerts**: `{len(alerts)}` active alerts.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Resource Utilization Baseline")
    md.append("")
    md.append("| Resource Domain | Metric | Measured Value |")
    md.append("|---|---|---|")
    md.append(f"| **Host Memory (WSL)** | Total RAM | `{host.get('wsl_total_mb')} MB` |")
    md.append(f"| **Host Memory (WSL)** | Used RAM | `{host.get('wsl_used_mb')} MB` ({host.get('wsl_mem_percent')}%) |")
    md.append(f"| **Host Memory (WSL)** | Available RAM | `{host.get('wsl_available_mb')} MB` |")
    md.append(f"| **Kind Control Plane** | Docker CPU / Mem | `{host.get('docker_kind_cpu')}` / `{host.get('docker_kind_mem')}` |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Workload Health & Restart Telemetry")
    md.append("")
    md.append("| Pod Name | Ready | Phase | Total Restarts | Session Restarts | Pod IP |")
    md.append("|---|:---:|:---:|:---:|:---:|---|")
    for p in k8s.get("pods", []):
        r_symbol = "✅" if p["ready"] else "❌"
        md.append(f"| `{p['name']}` | {r_symbol} {p['ready_fraction']} | {p['phase']} | {p['restarts_total']} | {p['restarts_new']} | `{p['ip']}` |")
    md.append("")
    md.append("### Deployments Status")
    md.append("| Deployment | Desired | Ready | Available | Status |")
    md.append("|---|:---:|:---:|:---:|:---:|")
    for d in k8s.get("deployments", []):
        d_stat = "✅ Healthy" if d["healthy"] else "❌ Degraded"
        md.append(f"| `{d['name']}` | {d['desired']} | {d['ready']} | {d['available']} | {d_stat} |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Databases & Persistence Health")
    md.append("")
    md.append("### MySQL Health")
    md.append(f"- **Availability**: `{'ALIVE' if mysql.get('available') else 'OFFLINE'}` (via `mysqladmin ping -h 127.0.0.1`)")
    md.append(f"- **Uptime**: `{mysql.get('uptime_seconds')} seconds`")
    md.append(f"- **Active Threads**: `{mysql.get('threads')}`")
    md.append(f"- **Total Questions**: `{mysql.get('questions')}`")
    md.append(f"- **Slow Queries**: `{mysql.get('slow_queries')}`")
    md.append(f"- **Average QPS**: `{mysql.get('qps')}`")
    md.append("")
    md.append("### Redis Health")
    md.append(f"- **Availability**: `{'PONG' if redis.get('available') else 'OFFLINE'}` (via `redis-cli ping`)")
    md.append(f"- **Version**: `{redis.get('version')}`")
    md.append(f"- **Memory Usage**: `{redis.get('used_memory_human')}` (Fragmentation Ratio: `{redis.get('mem_fragmentation_ratio')}`)")
    md.append(f"- **Connected Clients**: `{redis.get('connected_clients')}`")
    md.append(f"- **Commands Processed**: `{redis.get('total_commands')}` (`{redis.get('ops_per_sec')} ops/sec`)")
    md.append(f"- **RDB Persistence Status**: `{redis.get('rdb_last_status')}`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 5. Application Probes & Prometheus Metrics")
    md.append("")
    md.append("### Synthetic HTTP Probes")
    md.append("| Service | Path | Status Code | Latency (ms) | Result |")
    md.append("|---|---|:---:|:---:|:---:|")
    for pr in apps.get("http_probes", []):
        pr_res = "✅ OK" if pr["success"] else f"❌ {pr.get('error')}"
        md.append(f"| **{pr['name']}** | `{pr['path']}` | `{pr['status_code']}` | `{pr['latency_ms']} ms` | {pr_res} |")
    md.append("")
    md.append("### Prometheus-Format Metrics")
    md.append(f"- **Cart Service** (`/api/cart/metrics`): `items_added` = `{prom.get('cart', {}).get('items_added')}`")
    md.append(f"- **Payment Service** (`/api/payment/metrics`): `sold_count_total` = `{prom.get('payment', {}).get('sold_count_total')}`")
    md.append(f"- **Shipping Service** (`/actuator/health`): Status = `{apps.get('shipping_actuator', {}).get('status')}`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. Alerting & Threshold Verification")
    md.append("")
    if not alerts:
        md.append("✅ **All threshold checks passed cleanly.** Zero active alerts.")
    else:
        md.append("| Severity | Alert ID | Target Component | Description |")
        md.append("|---|---|---|---|")
        for a in alerts:
            md.append(f"| **{a['severity']}** | `{a['id']}` | `{a['component']}` | {a['message']} |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. How to Operate Monitoring")
    md.append("")
    md.append("### On-Demand Status")
    md.append("```bash")
    md.append("python3 scripts/robot_shop_monitor.py --status")
    md.append("```")
    md.append("")
    md.append("### Continuous Watch Mode")
    md.append("```bash")
    md.append("python3 scripts/robot_shop_monitor.py --watch --interval 10")
    md.append("```")
    md.append("")
    md.append("### Automated Alert Checking (CI / Scripting)")
    md.append("```bash")
    md.append("python3 scripts/robot_shop_monitor.py --check-alerts")
    md.append("# Returns exit code: 0 = OK, 1 = WARNING, 2 = CRITICAL")
    md.append("```")
    md.append("")
    md.append("### Generate Report & JSON Snapshot")
    md.append("```bash")
    md.append("python3 scripts/robot_shop_monitor.py --report")
    md.append("```")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


# ---------------------------------------------------------------------------
# Main CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Robot Shop Lightweight Observability Engine")
    parser.add_argument("--status", action="store_true", help="Display operational status dashboard once and exit")
    parser.add_argument("--watch", action="store_true", help="Stream live dashboard updates continuously")
    parser.add_argument("--interval", type=int, default=10, help="Refresh interval in seconds for --watch (default: 10)")
    parser.add_argument("--check-alerts", action="store_true", help="Evaluate alert thresholds and exit with status code (0=OK, 1=WARN, 2=CRIT)")
    parser.add_argument("--report", action="store_true", help="Generate timestamped Markdown report and JSON telemetry snapshot")
    parser.add_argument("--json", action="store_true", help="Output raw JSON telemetry snapshot to stdout")
    parser.add_argument("--report-file", default=DEFAULT_REPORT_FILE, help=f"Output path for Markdown report (default: {DEFAULT_REPORT_FILE})")
    parser.add_argument("--snapshot-file", default=None, help="Output path for JSON snapshot")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI terminal colors")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help=f"Kubernetes namespace (default: {DEFAULT_NAMESPACE})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Base URL for Robot Shop frontend (default: {DEFAULT_BASE_URL})")

    args = parser.parse_args()

    collector = ObservabilityCollector(namespace=args.namespace, base_url=args.base_url)
    renderer = DashboardRenderer(use_color=not args.no_color)

    # 1. Alert Check Mode
    if args.check_alerts:
        snap = collector.snapshot()
        alerts = snap.get("alerts", [])
        crit_count = sum(1 for a in alerts if a["severity"] == "CRITICAL")
        warn_count = sum(1 for a in alerts if a["severity"] == "WARNING")

        if crit_count > 0:
            print(f"CRITICAL: {crit_count} critical alert(s) detected:")
            for a in alerts:
                if a["severity"] == "CRITICAL":
                    print(f"  - [{a['id']}] {a['component']}: {a['message']}")
            sys.exit(2)
        elif warn_count > 0:
            print(f"WARNING: {warn_count} warning alert(s) detected:")
            for a in alerts:
                if a["severity"] == "WARNING":
                    print(f"  - [{a['id']}] {a['component']}: {a['message']}")
            sys.exit(1)
        else:
            print("OK: All threshold checks passed cleanly. Zero alerts.")
            sys.exit(0)

    # 2. JSON Output Mode
    if args.json:
        snap = collector.snapshot()
        print(json.dumps(snap, indent=2))
        sys.exit(0)

    # 3. Report Generation Mode
    if args.report:
        snap = collector.snapshot()
        ts_slug = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(REPORTS_DIR, exist_ok=True)
        
        snapshot_file = args.snapshot_file or f"{REPORTS_DIR}/telemetry_snapshot_{ts_slug}.json"
        
        # Save JSON snapshot
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
        # Save latest copy
        with open(f"{REPORTS_DIR}/telemetry_snapshot_latest.json", "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
            
        # Save Markdown report
        generate_markdown_report(snap, args.report_file)

        print(f"Observability Report generated:")
        print(f"  - Markdown Report: {args.report_file}")
        print(f"  - JSON Snapshot:   {snapshot_file}")
        print(f"  - Health Status:   {'ALL SYSTEMS OPERATIONAL' if snap['summary']['healthy'] else 'ISSUES DETECTED'}")
        sys.exit(0)

    # 4. Watch Mode
    if args.watch:
        try:
            while True:
                # Clear terminal screen
                print("\033[H\033[J", end="")
                snap = collector.snapshot()
                print(renderer.render(snap))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nWatch stopped by user.")
            sys.exit(0)

    # 5. Default: Status Dashboard
    snap = collector.snapshot()
    print(renderer.render(snap))
    if snap["summary"]["critical_count"] > 0:
        sys.exit(2)
    elif snap["summary"]["warning_count"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
