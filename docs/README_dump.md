# CityAirQ

uvicorn main:app --reload

json ingest:

{
  "clientId": "clientId-qwe123rty456uio789",
  "timestamp": 1718706400,
  "location": {
    "latitude": 40.712776,
    "longitude": 74.005974
  },
  "data": [
    {
      "dimension": "Temperature",
      "value": 27.1
    },
    {
      "dimension": "Humidity",
      "value": 61.3
    },
    {
      "dimension": "Pressure",
      "value": 1015.2
    },
    {
      "dimension": "Altitude",
      "value": 10.5
    },
    {
      "dimension": "CO2",
      "value": 720
    },
    {
      "dimension": "PM1.0",
      "value": 12.0
    },
    {
      "dimension": "PM2.5",
      "value": 17.8
    },
    {
      "dimension": "PM10",
      "value": 21.5
    }
  ]
}

{
  "clientId": "clientId-z98x76wv5432ut10",
  "timestamp": 1718702860,
  "location": {
    "latitude": 52.520008,
    "longitude": 13.404954
  },
  "data": [
    {
      "dimension": "Temperature",
      "value": 22.4
    },
    {
      "dimension": "Humidity",
      "value": 48.6
    },
    {
      "dimension": "Pressure",
      "value": 1009.8
    },
    {
      "dimension": "Altitude",
      "value": 34.2
    },
    {
      "dimension": "CO2",
      "value": 530
    },
    {
      "dimension": "PM1.0",
      "value": 8.7
    },
    {
      "dimension": "PM2.5",
      "value": 13.9
    },
    {
      "dimension": "PM10",
      "value": 19.4
    }
  ]
}


{
    "clientId": "clientId-a12b34cd5678ef90",
    "timestamp": 1718699260,
    "location": {
      "latitude": 45.764043,
      "longitude": 4.835659
    },
    "data": [
      {
        "dimension": "Temperature",
        "value": 30.5
      },
      {
        "dimension": "Humidity",
        "value": 55.2
      },
      {
        "dimension": "Pressure",
        "value": 1012.3
      },
      {
        "dimension": "Altitude",
        "value": 120.4
      },
      {
        "dimension": "CO2",
        "value": 600
      },
      {
        "dimension": "PM1.0",
        "value": 10.1
      },
      {
        "dimension": "PM2.5",
        "value": 15.3
      },
      {
        "dimension": "PM10",
        "value": 18.2
      }
    ]
  }

get:
{
  "latitude": 52.520008,
    "longitude": 13.404954,
  "radius": 0,
  "layers": ["Temperature", "Humidity", "Pressure", "Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
}

{
  "latitude": 45.764043,
  "longitude": 4.835659,
  "radius": 0,
  "layers": ["Temperature", "Humidity", "Pressure"]
}

{
  "latitude": 40.712776,
  "longitude": 74.005974,
  "radius": 0,
  "layers": ["Altitude", "CO2", "PM1_0", "PM2_5", "PM10"]
}

playground: https://developers.google.com/oauthplayground/?code=4%2F0AQSTgQF-FJ-JnbkGPaqJndWK0s-rUQ1-LE4sBhF6BVLKDQn_3Ucc1VuEWfANyRuDNaOjvA&scope=email+profile+openid+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.profile+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email&authuser=0&prompt=consent


QuestDB: LAST DEPLOYED: Fri Apr  4 14:04:04 2025
NAMESPACE: questdb
STATUS: deployed
REVISION: 1
NOTES:
1. Get the application URL by running these commands:
  export POD_NAME=$(kubectl get pods --namespace questdb -l "app.kubernetes.io/name=questdb,app.kubernetes.io/instance=questdb" -o jsonpath="{.items[0].metadata.name}")
  echo "Visit http://127.0.0.1:9000 to use your application"
  kubectl --namespace questdb port-forward $POD_NAME 9000:9000

gcloud auth activate-service-account --key-file=cityairq-pollution-project-gke_gcr-service-credentials.json   

gcloud container clusters get-credentials cityairq-cluster --zone us-west4 --project cityairq-pollution-project

kubectl create secret generic credentials-secret --from-file=credentials.json=/Users/dumitru.bianca/Documents/licenta/CityAirQ/credentials.json

  kubectl create namespace questdb

  helm install questdb questdb/questdb --namespace questdb

  kubectl get pod -n questdb -l app.kubernetes.io/name=questdb --show-labels (pentru a verifica labelul bazei de date)

  pt a te conecta la un container: kubectl exec -it ingest-service-68bbcb54b7-mcr5k -- /bin/bash

  kubectl rollout restart deployment [nume-deployment] -n [namespace]

  kubectl exec -it <numele_podului> -n <namespace> -- /bin/bash

  pip install --upgrade uvicorn h11 --> la database_service


  ----
  docker

  gcloud auth configure-docker

  docker buildx create --use 

  docker buildx bake -f docker-compose.buildx.yaml --push --set '*.platform=linux/amd64'

  ----

  Link portainer: http://34.22.177.97:9000/#!/1/kubernetes/dashboard
  --> i am specificat storage clas ul atunci cand l am descarcat

grafana: export POD_NAME=$(kubectl get pods --namespace monitoring -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=grafana" -o jsonpath="{.items[0].metadata.name}")
kubectl --namespace monitoring port-forward $POD_NAME 3000

kong: kubectl port-forward svc/kong-kong-admin -n kong 8001:8001

------------

prometheus: kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

user: admin
password: prom-operator

--

metrici client-message-handler: kubectl port-forward svc/client-message-handler 8000:8000 -n default
curl http://localhost:8000/metrics

--
UI prometheus: kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring
http://localhost:9090/targets

----------
loki: kubectl port-forward -n grafana-loki svc/loki-grafana 31007:80

user: admin

password: APw8Oe0r5K8MPoDlr3CSG4EtiRkzrgrovbqtA4Id

------
Auth cluster

gcloud auth activate-service-account \
  --key-file=/Users/dumitru.bianca/Documents/licenta/CityAirQ/deploy/cityairq-pollution-project-522aec65f650.json

gcloud config set project cityairq-pollution-project

 gcloud container clusters get-credentials cityairq-standard \
  --zone=europe-west1-b \                          
  --project=cityairq-pollution-project
----------
portainer pass: bibisitina123
link: https://130.211.76.121:9443

prometheus: kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
link: http://localhost:3000

loki: kubectl port-forward svc/loki-grafana -n monitoring 3000:80
link: http://localhost:3000

