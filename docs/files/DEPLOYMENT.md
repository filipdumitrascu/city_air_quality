# CityAirQ Deployment Guide

Detailed explanation of deployment scripts and commands.

## Docker Deployment

### docker-start.sh

Builds and starts all services locally using Docker Compose.

**What it does:**
1. Navigates to backend directory
2. Builds Docker images for all services using `docker-compose up -d --build`
3. Waits 10 seconds for services to initialize
4. Shows service status with `docker-compose ps`
5. Displays recent logs for verification

**Services started:**
- client-message-handler (port 8000)
- database-service (port 8002)
- ingest-service
- data-provider-service (port 8001)
- routing-service (port 8003)
- redis (port 6379)
- questdb (ports 9000, 9009)

**Usage:**
```bash
./scripts/docker-start.sh
```

### docker-stop.sh

Stops all running Docker containers.

**What it does:**
1. Runs `docker-compose down` to stop containers
2. Keeps volumes intact for data persistence

**Usage:**
```bash
./scripts/docker-stop.sh
```

### docker-clean.sh

Removes all Docker resources including volumes.

**What it does:**
1. Stops and removes containers with `docker-compose down -v`
2. Removes volumes (data will be lost)
3. Prunes dangling images with `docker image prune -f`

**Warning:** This deletes all data in volumes.

**Usage:**
```bash
./scripts/docker-clean.sh
```

### docker-logs.sh

Shows logs for services.

**What it does:**
1. If no service specified: shows logs for all services
2. If service specified: shows logs for that service only
3. Follows logs in real-time with `-f` flag

**Usage:**
```bash
# All services
./scripts/docker-logs.sh

# Specific service
./scripts/docker-logs.sh routing-service
```

## Kubernetes Deployment

### k8s-setup.sh

Configures kubectl to access your GKE cluster.

**What it does:**
1. Authenticates with Google Cloud using service account key
2. Sets active project with `gcloud config set project`
3. Gets cluster credentials with `gcloud container clusters get-credentials`
4. Verifies connection with `kubectl cluster-info`

**Prerequisites:**
- Service account JSON key in `deploy/` directory
- GKE cluster already created

**Configuration:**
Edit these variables in the script:
- PROJECT_ID: your Google Cloud project
- CLUSTER_NAME: your GKE cluster name
- ZONE: cluster zone
- SERVICE_ACCOUNT_KEY: path to JSON key

**Usage:**
```bash
./scripts/k8s-setup.sh
```

### k8s-deploy.sh

Deploys all services to Kubernetes cluster.

**What it does:**
1. Checks kubectl is configured
2. Creates Kubernetes secret from credentials.json
3. Deploys services in order:
   - Redis (with health check wait)
   - QuestDB
   - Database Service (with health check wait)
   - Ingest Service
   - Data Provider Service
   - Routing Service
   - Client Message Handler
   - Monitoring stack (Prometheus, Loki)
4. Waits for all deployments to be available
5. Shows pod status

**Usage:**
```bash
./scripts/k8s-deploy.sh
```

### k8s-delete.sh

Removes all services from Kubernetes cluster.

**What it does:**
1. Deletes deployments in reverse order
2. Uses `--ignore-not-found=true` to avoid errors if resources don't exist
3. Removes monitoring stack

**Note:** Does not delete PersistentVolumeClaims by default.

**Usage:**
```bash
./scripts/k8s-delete.sh
```

### k8s-status.sh

Shows status of all Kubernetes resources.

**What it does:**
Runs `kubectl get` for:
- Pods
- Services
- Deployments
- PersistentVolumeClaims
- ConfigMaps

**Usage:**
```bash
./scripts/k8s-status.sh
```

### k8s-logs.sh

Shows logs for a specific pod.

**What it does:**
1. If no pod name provided: lists available pods
2. If pod name provided: shows logs with `-f` (follow)

**Usage:**
```bash
# List pods
./scripts/k8s-logs.sh

# View logs
./scripts/k8s-logs.sh routing-service-7d9f8b6c4-xk2lp
```

## Build and Push

### build-push.sh

Builds Docker images and pushes to Google Artifact Registry.

**What it does:**
1. Authenticates with Google Container Registry using `gcloud auth configure-docker`
2. Creates or uses existing buildx builder for multi-platform builds
3. Builds images for linux/amd64 platform using `docker buildx bake`
4. Pushes images to Google Artifact Registry

**Prerequisites:**
- Authenticated with gcloud
- docker-compose.buildx.yaml configured with correct registry URLs

**Usage:**
```bash
./scripts/build-push.sh
```

## Common Workflows

### First Time Setup
```bash
# 1. Make scripts executable
chmod +x scripts/*.sh

# 2. Setup Kubernetes access
./scripts/k8s-setup.sh

# 3. Build and push images
./scripts/build-push.sh

# 4. Deploy to Kubernetes
./scripts/k8s-deploy.sh
```

### Local Development
```bash
# Start services
./scripts/docker-start.sh

# View logs
./scripts/docker-logs.sh routing-service

# Stop when done
./scripts/docker-stop.sh
```

### Update Deployment
```bash
# Rebuild and push images
./scripts/build-push.sh

# Restart deployment
kubectl rollout restart deployment routing-service
```

### Debugging
```bash
# Check pod status
./scripts/k8s-status.sh

# View pod logs
./scripts/k8s-logs.sh <pod-name>

# Access pod shell
kubectl exec -it <pod-name> -- /bin/bash
```

## Troubleshooting

### Docker Issues

**Problem:** Port already in use
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

**Problem:** Build fails
```bash
# Clean Docker cache
docker builder prune -a
./scripts/docker-clean.sh
./scripts/docker-start.sh
```

### Kubernetes Issues

**Problem:** Pods not starting
```bash
# Check pod details
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>
```

**Problem:** Authentication failed
```bash
# Re-run setup
./scripts/k8s-setup.sh
```

**Problem:** Image pull errors
```bash
# Verify images exist
gcloud container images list --repository=gcr.io/cityairq-pollution-project

# Rebuild and push
./scripts/build-push.sh
```
```
