# CityAirQ - Cloud Deployment Guide

## Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed and configured
- `kubectl` installed
- `docker` with buildx support
- Python 3.10+ with `psycopg2` for schema initialization

---

## Complete Setup (First Time)

### 1. Create Google Cloud Project (Browser)

1. Go to: https://console.cloud.google.com/projectcreate
2. Create new project:
   - Name: `cityairq-project` (or any name)
   - Note the **Project ID** (e.g., `elite-totem-484208-e2`)

### 2. Enable Required APIs (Browser)

Go to: https://console.cloud.google.com/apis/library?project=YOUR_PROJECT_ID

Enable these APIs:
- **Kubernetes Engine API**
- **Artifact Registry API**
- **Cloud Pub/Sub API**
- **Compute Engine API** (usually auto-enabled)

Or via CLI:
```bash
gcloud services enable container.googleapis.com \
    artifactregistry.googleapis.com \
    pubsub.googleapis.com \
    compute.googleapis.com \
    --project=YOUR_PROJECT_ID
```

### 3. Create Service Account (Browser)

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts?project=YOUR_PROJECT_ID
2. Click **CREATE SERVICE ACCOUNT**
3. Configure:
   - Name: `cityairq-deploy`
   - ID: `cityairq-deploy`
4. Click **CREATE AND CONTINUE**
5. Add roles:
   - `Kubernetes Engine Admin`
   - `Artifact Registry Administrator`
   - `Pub/Sub Publisher`
   - `Pub/Sub Subscriber`
   - `Storage Admin` (for Artifact Registry)
6. Click **DONE**
7. Click on the created service account
8. Go to **KEYS** tab → **ADD KEY** → **Create new key** → **JSON**
9. Save the downloaded file as `deploy/credentials.json`

### 4. Create Artifact Registry (Browser)

1. Go to: https://console.cloud.google.com/artifacts?project=YOUR_PROJECT_ID
2. Click **CREATE REPOSITORY**
3. Configure:
   - Name: `cityairq-images`
   - Format: `Docker`
   - Location type: `Region`
   - Region: `us-central1`
4. Click **CREATE**

### 5. Create Pub/Sub Topics and Subscriptions (Browser)

1. Go to: https://console.cloud.google.com/cloudpubsub/topic/list?project=YOUR_PROJECT_ID

2. Create 3 topics (click **CREATE TOPIC** for each):

   | Topic ID | Check "Add default subscription" |
   |----------|----------------------------------|
   | `ingest_service_messages` | Yes |
   | `results_service_messages` | Yes |
   | `results_response_messages` | Yes |

3. Go to **Subscriptions** tab and verify these exist:
   - `ingest_service_messages-sub`
   - `results_service_messages-sub`
   - `results_response_messages-sub`

   If names differ (e.g., `-sub-1`), rename them or update the code.

### 6. Create Kubernetes Cluster
```bash
gcloud auth login
```

```bash
gcloud config set project YOUR_PROJECT_ID
```

```bash
gcloud container clusters create cityairq-standard \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --num-nodes=2 \
    --disk-size=20 \
    --enable-autoscaling \
    --min-nodes=1 \
    --max-nodes=3 \
    --project=YOUR_PROJECT_ID
```

**Cost**: ~$18/week for this configuration

**For lower latency in Europe**, use:
```bash
--zone=europe-west1-b
# or
--zone=europe-central2-a
```

### 7. Routes API
1. Go to: https://console.cloud.google.com/apis/library?project=YOUR_PROJECT_ID

2. Find and enable `Routes API`

### 8. Update Configuration Files

Update these files with your Project ID:

**`scripts/cloud/setup.sh`**:
```bash
PROJECT_ID="YOUR_PROJECT_ID"
```

**`backend/common/message_queue_googlepubsub/pubsub_client.py`**:
```python
project_id = os.getenv("GCP_PROJECT_ID", "YOUR_PROJECT_ID")
```

**All deployment YAML files** in `deploy/`:
```yaml
env:
- name: GCP_PROJECT_ID
  value: "YOUR_PROJECT_ID"
```

**`docker-compose.buildx.yaml`** - update image registry paths:
```yaml
image: us-central1-docker.pkg.dev/YOUR_PROJECT_ID/cityairq-images/...
```

---

## Deployment Steps

### 1. Setup kubectl access
```bash
cd scripts/cloud
./setup.sh
```

### 2. Build and Push Images
```bash
./build-push.sh
```

### 3. Deploy to Kubernetes
```bash
./deploy.sh
```

### 4. Check Status
```bash
./info.sh
```

### 5. Get External IP
```bash
kubectl get service client-message-handler
```

### 6. Test
```bash
curl http://<EXTERNAL-IP>:8000/health
```

---

## After Code Modifications
```bash
./build-push.sh                    # Rebuild images
kubectl rollout restart deployment <service-name>  # Restart specific service
# OR
./clean.sh && ./deploy.sh          # Full redeploy
./info.sh                          # Check status
```

---

## Useful Commands

### View Logs
```bash
# Stdout logs
kubectl logs -l app=<service-name> --tail=50

# File logs (inside container)
kubectl exec -it $(kubectl get pods -l app=<service-name> -o jsonpath='{.items[0].metadata.name}') -- cat /app/logs/<service>.log
```

### Port Forward for Local Testing
```bash
# QuestDB
kubectl port-forward svc/questdb-service 8812:8812

# Database Service
kubectl port-forward svc/database-service 8001:8000

# Redis
kubectl port-forward svc/redis-service 6379:6379
```

### Access QuestDB Web UI
```bash
kubectl port-forward svc/questdb-service 9000:9000
# Open: http://localhost:9000
```

### Restart a Service
```bash
kubectl rollout restart deployment <deployment-name>
```

### Scale a Service
```bash
kubectl scale deployment <deployment-name> --replicas=3
```

---

## Cost Management

### Delete Cluster (Stop All Costs)
```bash
gcloud container clusters delete cityairq-standard \
    --zone=us-central1-a \
    --project=YOUR_PROJECT_ID \
    --quiet
```

### Pause Cluster (Reduce Costs)
Scale down to 0 nodes:
```bash
gcloud container clusters resize cityairq-standard \
    --zone=us-central1-a \
    --num-nodes=0 \
    --project=YOUR_PROJECT_ID
```

Resume:
```bash
gcloud container clusters resize cityairq-standard \
    --zone=us-central1-a \
    --num-nodes=2 \
    --project=YOUR_PROJECT_ID
```

---

## Checklist for New Project

When setting up on a new Google Cloud account:

- [ ] Create new project
- [ ] Enable APIs (Kubernetes, Artifact Registry, Pub/Sub, Compute)
- [ ] Create service account with roles:
  - [ ] Kubernetes Engine Admin
  - [ ] Artifact Registry Administrator
  - [ ] Pub/Sub Publisher
  - [ ] Pub/Sub Subscriber
  - [ ] Storage Admin
  - [ ] Storage Object Admin
  - [ ] Service Account User
- [ ] Download service account key → `deploy/credentials.json`
- [ ] Create Artifact Registry repository
- [ ] Create Pub/Sub topics and subscriptions
- [ ] Create Kubernetes cluster
- [ ] Update `PROJECT_ID` in:
  - [ ] `scripts/cloud/setup.sh`
  - [ ] `pubsub_client.py`
  - [ ] All deployment YAML files
  - [ ] `docker-compose.buildx.yaml`
- [ ] Run deployment steps
