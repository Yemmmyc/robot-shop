# Robot Shop Windows Access Guide

This guide describes the permanent, systemd-managed network bridge that enables seamless access to Stan's Robot Shop running in a local Kind Kubernetes cluster inside WSL2 directly from Windows web browsers.

---

## 1. Architecture & Traffic Flow

```
+-------------------------------------------------------------+
| Windows Host                                                |
|   Browser / curl: http://localhost:8080                     |
+------------------------------+------------------------------+
                               | (WSL2 localhost forwarding)
                               v
+-------------------------------------------------------------+
| WSL2 Ubuntu Environment                                    |
|   Listening: 127.0.0.1:8080 (Localhost only)                |
|   Service: robot-shop-bridge.service                        |
|   Process: scripts/robot_shop_bridge.py                     |
+------------------------------+------------------------------+
                               | (Dynamic Kind IP discovery)
                               v
+-------------------------------------------------------------+
| Docker 'kind' Bridge Network                                |
|   Container: capstone-cluster-control-plane                 |
|   Internal IP: Discovered via docker inspect (e.g. 172.24.0.2)
|   Target Port: Web NodePort (32521)                         |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Kubernetes Cluster                                          |
|   Namespace: robot-shop                                     |
|   Service: service/web (NodePort 32521 -> Container 8080)   |
|   Pod: web-xxxxxxxxxx-xxxxx (Nginx Frontend)                |
+-------------------------------------------------------------+
```

---

## 2. Key Features

1. **Pure Standard Library**: Implemented in Python 3 using only standard library modules (`socket`, `select`, `threading`, `subprocess`, `re`, `time`, `logging`, `signal`, `sys`). No external pip dependencies required.
2. **Dynamic Target Discovery**: Automatically inspects Docker on the `kind` network to discover the control-plane container IP. Never hardcodes IP addresses.
3. **Dynamic NodePort Validation**: Validates the active NodePort from Kubernetes service definitions with a safe fallback to 32521.
4. **Security by Default**: Binds strictly to `127.0.0.1:8080` to prevent unintended exposure to external networks.
5. **Resilient Error Handling**: Returns an informative **HTTP 503 Service Unavailable** page to browser clients when the cluster or container is temporarily down or restarting, rather than silently dropping connections.
6. **systemd Lifecycle**: Automatically managed as a background systemd service (`robot-shop-bridge.service`), auto-starting with WSL and restarting on failure.

---

## 3. Service Management Commands

All standard systemd commands apply:

### Check Status
```bash
systemctl status robot-shop-bridge.service
```

### View Live Logs
```bash
journalctl -u robot-shop-bridge.service -f
```

### View Recent Logs
```bash
journalctl -u robot-shop-bridge.service -n 25 --no-pager
```

### Restart Service
```bash
sudo systemctl restart robot-shop-bridge.service
```

### Stop Service
```bash
sudo systemctl stop robot-shop-bridge.service
```

### Start Service
```bash
sudo systemctl start robot-shop-bridge.service
```

### Disable Service (Prevent automatic start on boot)
```bash
sudo systemctl disable robot-shop-bridge.service
```

### Enable Service (Start automatically with WSL)
```bash
sudo systemctl enable robot-shop-bridge.service
```

---

## 4. How to Access Robot Shop from Windows

Once the service is active, open any Windows web browser (Chrome, Edge, Firefox) and navigate to:

👉 **[http://localhost:8080](http://localhost:8080)**

You can also test connectivity directly from Windows PowerShell:
```powershell
curl.exe -I http://localhost:8080
```
Expected output:
```text
HTTP/1.1 200 OK
Server: nginx/1.20.1
...
```

---

## 5. Troubleshooting & Runbook

### Problem 1: Port 8080 is already in use
If another application is using port 8080, identify the process:
```bash
fuser 8080/tcp
```
Inspect what process it is:
```bash
ps -fp $(fuser 8080/tcp 2>/dev/null)
```
Stop the conflicting process or reconfigure it.

### Problem 2: Browser returns HTTP 503 Service Unavailable
The bridge is running, but the Kind cluster container (`capstone-cluster-control-plane`) or the web service is not reachable.
1. Check if the Kind container is running:
   ```bash
   docker ps -f name=capstone-cluster-control-plane
   ```
2. Check if the Kubernetes web pod is Ready:
   ```bash
   kubectl get pods -l service=web -n robot-shop
   ```
3. Check the bridge journal for connection errors:
   ```bash
   journalctl -u robot-shop-bridge.service -n 20 --no-pager
   ```

### Problem 3: systemd is not enabled in WSL
Ensure `/etc/wsl.conf` contains:
```ini
[boot]
systemd=true
```
If modified, restart WSL from Windows PowerShell: `wsl --shutdown`.

---

## 6. Installed Files

- **Bridge Script**: `/home/yemmm/projects/robot-shop/scripts/robot_shop_bridge.py`
- **systemd Unit**: `/etc/systemd/system/robot-shop-bridge.service`
- **Documentation**: `/home/yemmm/projects/robot-shop/ACCESS_GUIDE.md`

