#!/bin/bash
# cleanup-monitoring.sh
# Remove monitoring stack

echo "Removing CityAirQ Monitoring Stack"

# Uninstall Helm releases
echo "Uninstalling Prometheus..."
helm uninstall prometheus -n monitoring 2>/dev/null || echo "Prometheus not found"

echo "Uninstalling Loki..."
helm uninstall loki -n monitoring 2>/dev/null || echo "Loki not found"

# Delete ServiceMonitors
echo "Deleting ServiceMonitors..."
kubectl delete -f prometheus/servicemonitor-cityairq.yaml 2>/dev/null || echo "ServiceMonitors not found"

# Delete ConfigMap
echo "Deleting dashboard ConfigMap..."
kubectl delete configmap cityairq-dashboard -n monitoring 2>/dev/null || echo "ConfigMap not found"

# Optionally delete namespace (this will delete everything in it)
read -p "Delete monitoring namespace? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl delete namespace monitoring
    echo "Monitoring namespace deleted"
else
    echo "Monitoring namespace preserved"
fi

echo ""
echo "Cleanup completed!"
