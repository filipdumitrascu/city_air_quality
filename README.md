# CityAirQ

# Contributors

* [Filip Dumitrascu](https://github.com/filipdumitrascu)

* [Bianca Dumitru](https://github.com/dbianca0907)

Steps for running the API server.

## Uploading all the microservices to Docker

All the microservices are containerized using Docker. It is a necessarry step for having them in the Google Artifact Registry. First you need to authenticate to Docker, then create a new buildx instance. The microservices are not built to be functional in the Docker containers, because of the dependendency with the client database_service.

Useful commands:

```
  gcloud auth configure-docker

  docker buildx create --use 

  docker buildx bake -f docker-compose.buildx.yaml --push --set '*.platform=linux/amd64' // the platform is specified in case of having a Mac with M1 chip
```
## Setup the Kubernetes cluster

You need a Google Cloud account and a project created. After that, you can create a Kubernetes cluster using Google Kubernetes Engine (GKE). You can follow the steps from. Make sure to create a cluster that doesn't have the memory handled by Google (don't choose the Autopilot mode). 

## Authenticate and get credentials for the cluster

To be able to interact with the cluster, you need to authenticate using a service account. You can create a service account from the Google Cloud Console, and download the JSON key file. After that, you can use the following commands to authenticate and get the credentials for the cluster:

```
gcloud auth activate-service-account \
  --key-file=/path/to/your/service-account-key.json
gcloud config set project your-project-id
gcloud container clusters get-credentials cityairq-standard \
  --zone=europe-west1-b \                          
  --project=cityairq-pollution-project // replace the information with your project details
```
## Deploy the microservices to the cluster
You can use kubectl to deploy the microservices to the cluster. Make sure you have the kubectl tool installed and configured to interact with your cluster. Useful commands:

```
kubectl create secret generic credentials-secret --from-file=credentials.json=/path/to/your/credentials.json
kubectl apply -f deployment_file
kubectl rollout restart deployment [deployment-name] -n [namespace] // to restart a deployment
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash // to access a pod
```

Also make sure to update the ip addresses in the deployment files for the database_service and the questdb_service to point to the correct database instances.
