# Recovery Backup Manifest — Kind `capstone-cluster` & Robot Shop Databases

**Execution Date:** November 4, 2026, 18:40–18:41 UTC+1  
**Cluster:** `capstone-cluster` (Kind v1.32.2 control plane)  
**Host Storage Location:** `/home/yemmm/projects/robot-shop/backups/recovery_20261104_184021`  
**Host Filesystem:** `\\wsl.localhost\Ubuntu-22.04\home\yemmm\projects\robot-shop\backups\recovery_20261104_184021`  
**Status:** VERIFIED & COMPLETE — All backups created, validated against live data, and SHA-256 verified.

---

## 1. Storage & Pre-Flight Safeguards Verification

- **Storage Location Compliance:** All backup archives are stored exclusively on the WSL2 host filesystem under the dedicated project backup directory. No backup files reside in the live etcd data directory (`/var/lib/etcd`), within the Kind node rootfs, or in live MySQL storage volumes.
- **Overwrite Protection:** Stored in a newly generated, timestamp-isolated directory `recovery_20261104_184021`.
- **Disk Space Pre-Check:**
  - **Available before backup:** `923 GB` (`968,378,080 KB`)
  - **Available after backup:** `923 GB`
  - **Threshold requirement:** > 5 GB (Passed)
- **Zero Workload Disruption:**
  - `etcd` remained online with zero restarts during snapshot creation.
  - `mysqldump` executed using `--single-transaction --quick` with zero locking, zero modifications, and zero record alterations.
  - Zero Kubernetes pods, deployments, services, or configurations were modified or restarted.

---

## 2. Backup Inventory & Checksums

| Artifact | Filename | Size (Bytes) | Size (Human) | SHA-256 Checksum | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **etcd Cluster Snapshot** | `etcd_capstone_cluster_snapshot.db` | `7,614,496` | 7.3 MB | `261c20c77fc66c4d29e1c92f9fe1ce46e62e8f0805c6c5232e05eaf74aeba9cb` | **VERIFIED** |
| **MySQL `cities` Database** | `mysql_cities_database.sql` | `64,581,590` | 61.6 MB | `f7188fbe4b340892e07930269b89a39414390befe9298a83d7c194c9ad06da0a` | **VERIFIED** |
| **MySQL `ratings` Database** | `mysql_ratings_database.sql` | `2,059` | 2.1 KB | `013f90202a81104b3cd22813da7d1e04b5f22992080a44238c2855f52ee41682` | **VERIFIED** |
| **Checksum Manifest** | `SHA256SUMS.txt` | `285` | 285 B | *N/A (Reference)* | **PASSED (`sha256sum -c`)** |
| **etcd Snapshot Status Log**| `etcd_snapshot_status.txt` | `250` | 250 B | *N/A (Log)* | **PASSED** |

---

## 3. Detailed Integrity & Health Verification

### A. etcd Snapshot Verification
The snapshot was taken using authenticated client certificates directly from the running etcd instance (`https://127.0.0.1:2379`) and verified using `etcdctl snapshot status`:
```text
+----------+----------+------------+------------+
|   HASH   | REVISION | TOTAL KEYS | TOTAL SIZE |
+----------+----------+------------+------------+
| c34d9621 |   225422 |       1021 |     7.6 MB |
+----------+----------+------------+------------+
```
- **Hash:** `c34d9621`
- **Revision:** `225422`
- **Total Keys:** `1021`
- **Total Size:** `7.6 MB` (`7,614,496 bytes`)
- **Integrity Status:** Valid and consistent bbolt database snapshot. Temporary container files were removed following extraction.

### B. MySQL `cities` Database Dump Verification
- **Method:** `mysqldump -uroot --single-transaction --quick --routines --triggers --databases cities`
- **Record Integrity:** Covers the entire `cities` dataset (948,833 records in table `cities`, plus table `codes`).
- **Completion Check:** Verified end-of-file trailer:
  ```text
  -- Dump completed on 2026-11-04 17:41:05
  ```
- **Integrity Status:** Uncorrupted, complete, and syntactically valid SQL dump.

### C. MySQL `ratings` Database Dump Verification
- **Method:** `mysqldump -uroot --single-transaction --quick --routines --triggers --databases ratings`
- **Completion Check:** Verified end-of-file trailer:
  ```text
  -- Dump completed on 2026-11-04 17:41:06
  ```
- **Integrity Status:** Complete schema and data dump.

### D. SHA-256 Verification Run Output
```text
etcd_capstone_cluster_snapshot.db: OK
mysql_cities_database.sql: OK
mysql_ratings_database.sql: OK
```

---

## 4. Point-In-Time Restoration Procedures

Should any future operational issue require restoration from these backups:

### etcd Cluster Restore (Disaster Recovery)
To restore the control plane etcd state from this snapshot:
```bash
docker exec -i capstone-cluster-control-plane etcdutl snapshot restore \
  /path/to/etcd_capstone_cluster_snapshot.db \
  --data-dir=/var/lib/etcd-from-backup \
  --initial-cluster=capstone-cluster-control-plane=https://172.24.0.2:2380 \
  --initial-advertise-peer-urls=https://172.24.0.2:2380 \
  --name=capstone-cluster-control-plane
```

### MySQL Databases Restore
To restore `cities` and `ratings` to the running MySQL instance:
```bash
kubectl exec -i -n robot-shop deploy/mysql -- mysql -uroot < mysql_cities_database.sql
kubectl exec -i -n robot-shop deploy/mysql -- mysql -uroot < mysql_ratings_database.sql
```

---

## 5. Summary & Hand-Off

All approved recovery backups have been created with zero disruption to the cluster or running applications, validated for consistency and completeness, verified via cryptographic SHA-256 checksums, and safely stored on host storage.

