# Sample Microservice Application

Stan's Robot Shop is a sample microservice application you can use as a sandbox to test and learn containerised application orchestration and monitoring techniques. It is not intended to be a comprehensive reference example of how to write a microservices application, although you will better understand some of those concepts by playing with Stan's Robot Shop. To be clear, the error handling is patchy and there is not any security built into the application.

You can get more detailed information from my [blog post](https://www.instana.com/blog/stans-robot-shop-sample-microservice-application/) about this sample microservice application.

This sample microservice application has been built using these technologies:
- NodeJS ([Express](http://expressjs.com/))
- Java ([Spring Boot](https://spring.io/))
- Python ([Flask](http://flask.pocoo.org))
- Golang
- PHP (Apache)
- MongoDB
- Redis
- MySQL ([Maxmind](http://www.maxmind.com) data)
- RabbitMQ
- Nginx
- AngularJS (1.x)

The various services in the sample application already include all required Instana components installed and configured. The Instana components provide automatic instrumentation for complete end to end [tracing](https://docs.instana.io/core_concepts/tracing/), as well as complete visibility into time series metrics for all the technologies.

To see the application performance results in the Instana dashboard, you will first need an Instana account. Don't worry a [trial account](https://instana.com/trial?utm_source=github&utm_medium=robot_shop) is free.

## Build from Source
To optionally build from source (you will need a newish version of Docker to do this) use Docker Compose. Optionally edit the `.env` file to specify an alternative image registry and version tag; see the official [documentation](https://docs.docker.com/compose/env-file/) for more information.

To download the tracing module for Nginx, it needs a valid Instana agent key. Set this in the environment before starting the build.

```shell
$ export INSTANA_AGENT_KEY="<your agent key>"
```

Now build all the images.

```shell
$ docker-compose build
```

If you modified the `.env` file and changed the image registry, you need to push the images to that registry

```shell
$ docker-compose push
```

## Run Locally
You can run it locally for testing.

If you did not build from source, don't worry all the images are on Docker Hub. Just pull down those images first using:

```shell
$ docker-compose pull
```

Fire up Stan's Robot Shop with:

```shell
$ docker-compose up
```

If you want to fire up some load as well:

```shell
$ docker-compose -f docker-compose.yaml -f docker-compose-load.yaml up
```

If you are running it locally on a Linux host you can also run the Instana [agent](https://docs.instana.io/quick_start/agent_setup/container/docker/) locally, unfortunately the agent is currently not supported on Mac.

There is also only limited support on ARM architectures at the moment.

## Marathon / DCOS

The manifests for robotshop are in the *DCOS/* directory. These manifests were built using a fresh install of DCOS 1.11.0. They should work on a vanilla HA or single instance install.

You may install Instana via the DCOS package manager, instructions are here: https://github.com/dcos/examples/tree/master/instana-agent/1.9

## Kubernetes
You can run Kubernetes locally using [minikube](https://github.com/kubernetes/minikube) or on one of the many cloud providers.

The Docker container images are all available on [Docker Hub](https://hub.docker.com/u/robotshop/).

Install Stan's Robot Shop to your Kubernetes cluster using the [Helm](K8s/helm/README.md) chart.

To deploy the Instana agent to Kubernetes, just use the [helm](https://github.com/instana/helm-charts) chart.

## Accessing the Store
If you are running the store locally via *docker-compose up* then, the store front is available on localhost port 8080 [http://localhost:8080](http://localhost:8080/)

If you are running the store on Kubernetes via minikube then, find the IP address of Minikube and the Node Port of the web service.

```shell
$ minikube ip
$ kubectl get svc web
```

If you are using a cloud Kubernetes / Openshift / Mesosphere then it will be available on the load balancer of that system.

### Windows & WSL (Kind Cluster Access)
When running inside WSL2 on a local Kind cluster (`capstone-cluster`), access the storefront directly from Windows browsers at **[http://localhost:8080](http://localhost:8080)** via the permanent, systemd-managed network bridge (`robot-shop-bridge.service`).

For complete architecture, service lifecycle commands, and troubleshooting, see the [Windows Access Guide](ACCESS_GUIDE.md).

## Load Generation
A separate load generation utility is provided in the `load-gen` directory. This is not automatically run when the application is started. The load generator is built with Python and [Locust](https://locust.io). The `build.sh` script builds the Docker image, optionally taking *push* as the first argument to also push the image to the registry. The registry and tag settings are loaded from the `.env` file in the parent directory. The script `load-gen.sh` runs the image, it takes a number of command line arguments. You could run the container inside an orchestration system (K8s) as well if you want to, an example descriptor is provided in K8s directory. For End-user Monitoring ,load is not automatically generated but by navigating through the Robotshop from the browser .For more details see the [README](load-gen/README.md) in the load-gen directory.  

## Website Monitoring / End-User Monitoring

### Docker Compose

To enable Website Monioring / End-User Monitoring (EUM) see the official [documentation](https://docs.instana.io/website_monitoring/) for how to create a configuration. There is no need to inject the JavaScript fragment into the page, this will be handled automatically. Just make a note of the unique key and set the environment variable `INSTANA_EUM_KEY` and `INSTANA_EUM_REPORTING_URL` for the web image within `docker-compose.yaml`.

### Kubernetes

The Helm chart for installing Stan's Robot Shop supports setting the key and endpoint url required for website monitoring, see the [README](K8s/helm/README.md).

## Prometheus

The cart and payment services both have Prometheus metric endpoints. These are accessible on `/metrics`. The cart service provides:

* Counter of the number of items added to the cart

The payment services provides:

* Counter of the number of items perchased
* Histogram of the total number of items in each cart
* Histogram of the total value of each cart

To test the metrics use:

```shell
$ curl http://<host>:8080/api/cart/metrics
$ curl http://<host>:8080/api/payment/metrics
```

---

# DevOps Capstone 2: Keep It Running (Stan's Robot Shop)

This repository contains the complete implementation, operational runbooks, incident postmortems, and observability configurations for **DevOps Engineering Capstone 2 (Keep It Running)** at TS Academy.

## 1. Architecture & Technology Stack

Stan's Robot Shop is a distributed multi-tier e-commerce microservices application deployed to Kubernetes (`robot-shop` namespace):

```
                        [Customer Browser / Ingress]
                                     │
                             (NodePort 32521)
                                     ▼
                                ┌─────────┐
                                │   web   │ (Nginx / Angular UI Gateway)
                                └────┬────┘
         ┌───────────────────┬───────┴───────────┬────────────────────┐
         ▼                   ▼                   ▼                    ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐        ┌───────────┐
   │ catalogue │       │   user    │       │   cart    │        │ shipping  │
   │  (NodeJS) │       │  (NodeJS) │       │  (NodeJS) │        │ (Java SB) │
   └─────┬─────┘       └─────┬─────┘       └─────┬─────┘        └─────┬─────┘
         ▼                   ▼                   ▼                    ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐        ┌───────────┐
   │  MongoDB  │       │  MongoDB  │       │   Redis   │        │   MySQL   │
   └───────────┘       └───────────┘       └─────┬─────┘        └───────────┘
                                                 ▼
                                           ┌───────────┐        ┌───────────┐
                                           │  payment  ├───────►│ RabbitMQ  │
                                           │ (Python)  │        └─────┬─────┘
                                           └───────────┘              ▼
                                                                ┌───────────┐
                                                                │ dispatch  │
                                                                │  (Golang) │
                                                                └───────────┘
```

* **Microservices**: `web` (Nginx), `catalogue` (Node.js), `user` (Node.js), `cart` (Node.js), `shipping` (Java Spring Boot), `payment` (Python Flask/uWSGI), `ratings` (PHP/Apache), `dispatch` (Go).
* **Datastores & Brokers**: MySQL 5.7, MongoDB 3.4, Redis 4.0, RabbitMQ 3.7.
* **Orchestration**: Kubernetes v1.32.2 on Kind (`capstone-cluster`) co-tenanted with Capstone 1 (`example-voting-app`).

## 2. Prerequisites & Deployment Instructions

### Prerequisites
* Windows 11 with WSL2 (Ubuntu 22.04 LTS).
* Docker Engine & Kind (`kind version 0.27.0+`).
* `kubectl` and `helm v3.x`.
* Python 3.10+ (Standard Library only; zero external pip dependencies).

### Helm Deployment
```bash
# Verify cluster context
kubectl cluster-info --context kind-capstone-cluster

# Deploy Robot Shop chart to robot-shop namespace
helm upgrade --install robot-shop ./K8s/helm \
  --namespace robot-shop \
  --create-namespace \
  -f ./K8s/helm/values.yaml

# Verify all 12 pods reach 1/1 Running status
kubectl get pods -n robot-shop
```

## 3. Verification & Automated Testing

A self-contained test engine using Python standard library verifies service health, business logic, negative scenarios, and SLO latency thresholds:

```bash
# 1. Run full automated smoke test suite (12 microservices + datastores)
python3 scripts/robot_shop_test_suite.py --smoke --base-url http://172.24.0.2:32521

# 2. Run full end-to-end customer journey & negative validation
python3 scripts/robot_shop_test_suite.py --all --report --base-url http://172.24.0.2:32521
```

* **Current Verified Status**: 13/13 Smoke Tests Passing (100%), p50 latency 85 ms, p95 latency < 1,500 ms.

## 4. Monitoring & Telemetry Inspection

Non-invasive monitoring and alerting telemetry is provided by `robot_shop_monitor.py`:

```bash
# Check instantaneous cluster and datastore health
python3 scripts/robot_shop_monitor.py --status --base-url http://172.24.0.2:32521

# Evaluate alerting rules and print active warnings/critical alerts
python3 scripts/robot_shop_monitor.py --check-alerts --base-url http://172.24.0.2:32521
```

## 5. Service Level Objectives (SLO) & Error Budget Summary

* **Availability SLI**: Ratio of successful HTTP responses (2xx/3xx) over total valid requests.
* **Availability SLO Target**: **$\ge 99.0\%$** measured over a 30-day rolling window.
* **Error Budget**: **$1.0\%$** = **432 minutes** (7 hours 12 minutes) of allowable downtime per 30-day window ($43,200\text{ min} \times 0.01 = 432\text{ min}$).
* **Multi-Window Burn-Rate Alerting**:
  * **Critical (SEV-1)**: $14.4\times$ burn rate (consumes 2% of budget in 1 hour).
  * **Warning (SEV-2)**: $6.0\times$ burn rate (consumes 5% of budget in 6 hours).
* Full policy documented in [`SLO.md`](SLO.md).

## 6. Incident Drill Summary (Step 6)

* **Target**: Stateless `payment` microservice.
* **Execution**: Scaled `payment` deployment to 0 replicas; monitor immediately triggered critical alert `[SERVICE_NO_ENDPOINTS] payment`.
* **Remediation**: Deployment scaled back to 1 replica; rollout completed in 24 seconds, and smoke test suite verified 100% recovery (13/13 passing).
* Full step-by-step logs documented in [`INCIDENT_DRILL_REPORT.md`](INCIDENT_DRILL_REPORT.md).

## 7. Official Hand-in Deliverables Directory (Page 8 Checklist)

| Item | Deliverable Description | Repository File |
| :---: | :--- | :--- |
| **1** | **Dashboard exported as code** | [`dashboards/robot-shop-dashboard.json`](dashboards/robot-shop-dashboard.json) |
| **2** | **Logging & tracing configuration** | [`observability/logging/fluent-bit-loki.yaml`](observability/logging/fluent-bit-loki.yaml)<br>[`observability/tracing/otel-collector-jaeger.yaml`](observability/tracing/otel-collector-jaeger.yaml) |
| **3** | **SLO document with error budget** | [`SLO.md`](SLO.md) |
| **4** | **Blameless postmortem** | [`INCIDENT_POSTMORTEM.md`](INCIDENT_POSTMORTEM.md) |
| **5** | **Evidence of alert firing during drill** | [`INCIDENT_DRILL_REPORT.md`](INCIDENT_DRILL_REPORT.md) |
| **6** | **Evidence of real distributed trace** | [`OBSERVABILITY_EVIDENCE.md`](OBSERVABILITY_EVIDENCE.md) (Section 3) |
| **7** | **Evidence of logs searchable by service/level**| [`OBSERVABILITY_EVIDENCE.md`](OBSERVABILITY_EVIDENCE.md) (Section 2) |
| **8** | **SRE operational runbook linked from alert** | [`RUNBOOK.md`](RUNBOOK.md) |

### Supporting Configuration & Reports
* **Alertmanager & Prometheus Rules**: [`observability/alerting/alerts.yaml`](observability/alerting/alerts.yaml)
* **Cryptographic Backup Manifest**: [`RECOVERY_BACKUP_MANIFEST.md`](RECOVERY_BACKUP_MANIFEST.md)
* **Cluster Recovery Assessment**: [`KUBERNETES_RECOVERY_ASSESSMENT.md`](KUBERNETES_RECOVERY_ASSESSMENT.md)

## 8. Known Limitations & Resource Constraints

* **Environment Ceiling**: WSL2 VM memory is constrained to 4.8 GiB, with the Kind single-node control-plane container consuming 2.675 GiB (55.7% of total RAM).
* **Observability Hosting Constraint**: Full live deployment of `kube-prometheus-stack`, Loki, and Jaeger daemons requires an additional >3.5 GiB of RAM. Burst CPU load trips Kubelet's 15-second `/livez` probe, resulting in `kube-apiserver` restarts (exit code 137). To protect cluster stability, observability components are verified as production-grade configurations as code. Live daemon execution requires a multi-node cluster or $\ge 8\text{ GiB}$ host memory.
