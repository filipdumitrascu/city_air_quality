# Flow Deployment (first time)

## 1. Create Cluster (cost ~18$ per week)
```bash
gcloud container clusters create cityairq-standard \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --num-nodes=2 \
    --disk-size=20 \
    --enable-autoscaling \
    --min-nodes=2 \
    --max-nodes=3 \
    --project=elite-totem-484208-e2
```

## 2. Setup
``` bash
./setup.sh
```

## 3. Create artifact registry
Browser: https://console.cloud.google.com/artifacts?project=elite-totem-484208-e2

CREATE REPOSITORY:
-   Name: cityairq-images
-   Format: Docker
-   Region: us-central1

Authenticate Docker :
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

## 4. Build and Push Images 
```bash
./build-push.sh
```

## 5. Deploy
```bash
./deploy
```

## 6. Status
```bash
./info.sh
```

## Get external IP
kubectl get service client-message-handler

## Test
curl http://<EXTERNAL-IP>:8000/health


# After modifications

```bash
./build-push.sh
./clean.sh  # deletes deployment for restart, not the cluster
./deploy.sh
./info.sh
```


# No cost (delete cluster)
```bashrc
gcloud container clusters delete cityairq-standard \
    --zone=us-central1-a \
    --project=elite-totem-484208-e2 \
    --quiet
```
