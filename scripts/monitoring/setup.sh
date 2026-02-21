#!/bin/bash
# setup-monitoring.sh
# Installs complete monitoring stack: Prometheus, Grafana, Loki

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "CityAirQ Monitoring Stack Setup"

# Create monitoring namespace
echo ""
echo "Creating monitoring namespace..."
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Add Helm repositories
echo ""
echo "Adding Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack (includes Prometheus, Grafana, Alertmanager)
echo ""
echo "Installing Prometheus stack..."
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --values "$SCRIPT_DIR/../../monitoring/prometheus/prometheus-values.yaml" \
    --wait --timeout 10m

# Install Loki stack (for log aggregation)
echo ""
echo "Installing Loki stack..."
helm upgrade --install loki grafana/loki-stack \
    --namespace monitoring \
    --values "$SCRIPT_DIR/../../monitoring/loki/loki-values.yaml" \
    --wait --timeout 5m

# Apply ServiceMonitors for CityAirQ services
echo ""
echo "Applying ServiceMonitors..."
kubectl apply -f "$SCRIPT_DIR/../../monitoring/prometheus/servicemonitor-cityairq.yaml"

# Add Loki as datasource in prometheus-grafana
echo ""
echo "Adding Loki datasource to Grafana..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasource-loki
  namespace: monitoring
  labels:
    grafana_datasource: "1"
data:
  loki-datasource.yaml: |
    apiVersion: 1
    datasources:
      - name: Loki
        type: loki
        access: proxy
        url: http://loki:3100
        isDefault: false
        jsonData:
          maxLines: 1000
EOF

# Create ConfigMaps for Grafana dashboards
echo ""
echo "Creating Grafana dashboard ConfigMaps..."

# Metrics Dashboard
kubectl create configmap cityairq-metrics-dashboard \
    --from-file=cityairq-metrics-dashboard.json="$SCRIPT_DIR/../../monitoring/grafana/cityairq-metrics-dashboard.json" \
    --namespace monitoring \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl label configmap cityairq-metrics-dashboard \
    --namespace monitoring \
    grafana_dashboard=1 \
    --overwrite

# Logs Dashboard
kubectl create configmap cityairq-logs-dashboard \
    --from-file=cityairq-logs-dashboard.json="$SCRIPT_DIR/../../monitoring/grafana/cityairq-logs-dashboard.json" \
    --namespace monitoring \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl label configmap cityairq-logs-dashboard \
    --namespace monitoring \
    grafana_dashboard=1 \
    --overwrite

# Wait for pods to be ready
echo ""
echo "Waiting for monitoring pods to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n monitoring --timeout=300s || echo "Grafana not ready yet"
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=prometheus -n monitoring --timeout=300s || echo "Prometheus not ready yet"

# Restart Grafana to pick up new dashboards
echo ""
echo "Restarting Grafana to load dashboards..."
kubectl rollout restart deployment prometheus-grafana -n monitoring
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n monitoring --timeout=120s || echo "Grafana restart pending"

# Get Grafana credentials and URL
echo ""
echo "Monitoring Stack Installed Successfully!"
echo ""

# Get Grafana admin password
GRAFANA_PASSWORD=$(kubectl get secret --namespace monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" 2>/dev/null | base64 --decode) || GRAFANA_PASSWORD="cityairq-admin"

# Get Grafana external IP
GRAFANA_IP=$(kubectl get svc prometheus-grafana -n monitoring -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")

echo "Grafana:"
echo "  URL: http://${GRAFANA_IP}:80"
echo "  Username: admin"
echo "  Password: ${GRAFANA_PASSWORD}"
echo ""
echo "Dashboards installed:"
echo "  - CityAirQ Metrics Dashboard (HTTP requests, CPU, Memory, Latency)"
echo "  - CityAirQ Logs Dashboard (Loki logs per service)"
echo ""

# Get Prometheus URL
echo "Prometheus:"
echo "  Port-forward: kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090"
echo ""

echo "Loki:"
echo "  Port-forward: kubectl port-forward svc/loki -n monitoring 3100:3100"
echo ""

echo "To view all monitoring pods:"
echo "  kubectl get pods -n monitoring"
echo ""
