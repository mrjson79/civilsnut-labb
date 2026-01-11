# Victoria Metrics K8s Stack Migration

This directory contains the migration from `kube-prometheus-stack` to `victoria-metrics-k8s-stack` for monitoring infrastructure.

## Overview

Victoria Metrics is a fast, cost-effective monitoring solution that is compatible with Prometheus but offers better performance, lower resource usage, and improved storage efficiency.

### Key Benefits

- **Better Performance**: Up to 20x faster ingestion and queries compared to Prometheus
- **Lower Resource Usage**: Significantly reduced memory and CPU consumption
- **Cost Effective**: Better compression ratios and storage efficiency
- **Prometheus Compatible**: Drop-in replacement with full PromQL support
- **Scalable**: Better handling of high cardinality metrics

## Architecture Components

### Core Components

- **VMSingle**: Single-node VictoriaMetrics instance (replaces Prometheus)
- **VMAgent**: Metrics collection agent (replaces Prometheus scraping)
- **VMAlert**: Alerting engine (replaces Prometheus alerting rules)
- **AlertManager**: Alert routing and notification (same as before)
- **Grafana**: Visualization (same as before, with VM as datasource)

### Monitoring Targets

- **Node Exporter**: System metrics from all nodes
- **Kube State Metrics**: Kubernetes object state metrics
- **Cilium**: CNI and Gateway API metrics
- **FluxCD**: GitOps controller metrics
- **Gateway API**: Ingress and routing metrics

## Migration Steps

### 1. Backup Current Data (Optional)

```bash
# Export current Prometheus data if needed
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Use Prometheus API to export data or take volume snapshots
```

### 2. Apply Victoria Metrics Stack

```bash
# Apply the new stack
kubectl apply -k fluxcd/vm-stack/

# Monitor deployment
kubectl get pods -n monitoring -w
```

### 3. Verify Services

```bash
# Check VMSingle
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-k8s-stack 8429:8429

# Check VMAgent
kubectl logs -n monitoring -l app.kubernetes.io/name=vmagent

# Check Grafana
kubectl port-forward -n monitoring svc/vm-grafana 3000:80
```

### 4. Remove Old Stack (After Verification)

```bash
# Remove the old kube-prometheus-stack
kubectl delete -k fluxcd/kube-prometheus/
```

## Configuration Details

### Storage Configuration

```yaml
vmsingle:
  spec:
    storage:
      storageClassName: longhorn
      accessModes: [ReadWriteOnce]
      resources:
        requests:
          storage: 50Gi
    retentionPeriod: "10"  # 10 months retention
```

### Resource Limits

- **VMSingle**: 2-4Gi memory, 1-2 CPU cores
- **VMAgent**: 512Mi-1Gi memory, 250-500m CPU
- **VMAlert**: 128-256Mi memory, 100-200m CPU
- **Grafana**: 256-512Mi memory, 100-200m CPU

### Custom Scrape Configurations

Additional scrape configs are defined in `configs/additional-scrape-configs.yaml`:

- Cilium agent metrics on port 9965
- Custom application metrics as needed

## Service Discovery

### VMServiceScrape (replaces ServiceMonitor)

Automatically discovers and scrapes services with matching labels:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMServiceScrape
metadata:
  name: my-app
spec:
  selector:
    matchLabels:
      app: my-app
  endpoints:
    - port: metrics
```

### VMPodScrape (replaces PodMonitor)

Scrapes pods directly, useful for DaemonSets and system components:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMPodScrape
metadata:
  name: system-pods
spec:
  selector:
    matchLabels:
      tier: system
```

## Alerting Rules

### VMRule (replaces PrometheusRule)

Alert and recording rules are defined as VMRule resources:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMRule
metadata:
  name: my-alerts
spec:
  groups:
    - name: my-group
      rules:
        - alert: HighErrorRate
          expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
```

## Dashboards

### Pre-configured Dashboards

The following dashboards are automatically imported:

**Kubernetes:**
- API Server metrics
- CoreDNS metrics
- Node, Pod, and Namespace views

**Cilium/Gateway API:**
- Cilium agent and operator metrics
- Hubble flow metrics
- Gateway and HTTPRoute status

**FluxCD:**
- GitOps controller metrics
- Cluster reconciliation status

**Victoria Metrics:**
- VMSingle performance metrics
- VMAgent scraping metrics
- VMAlert rule evaluation

### Custom Dashboards

Add custom dashboards by extending the Grafana configuration:

```yaml
grafana:
  dashboards:
    my-dashboards:
      my-dashboard:
        url: https://example.com/dashboard.json
```

## Monitoring and Troubleshooting

### Health Checks

```bash
# Check VMSingle health
curl http://localhost:8429/health

# Check VMAgent targets
curl http://localhost:8429/api/v1/targets

# Check VMAlert rules
curl http://localhost:8429/api/v1/rules
```

### Common Issues

1. **High Memory Usage**: Increase VMSingle memory limits
2. **Scrape Failures**: Check service discovery and network policies
3. **Missing Metrics**: Verify VMServiceScrape/VMPodScrape labels
4. **Dashboard Issues**: Check Grafana datasource configuration

### Performance Tuning

```yaml
vmsingle:
  spec:
    extraArgs:
      maxConcurrentInserts: "8"
      maxLabelsPerTimeseries: "30"
      maxSamplesPerQuery: "50000000"
```

## Accessing Services

### Grafana Dashboard

Access via HTTPRoute: `https://grafana.civilsnut.se`

Default login: `admin` / (check secret for password)

### Direct Access (Port Forward)

```bash
# Grafana
kubectl port-forward -n monitoring svc/vm-grafana 3000:80

# VMSingle (Prometheus-compatible API)
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-k8s-stack 8429:8429

# AlertManager
kubectl port-forward -n monitoring svc/vmalertmanager-victoria-metrics-k8s-stack 9093:9093
```

## Backup and Restore

### Creating Backups

```bash
# Create snapshot
curl -X POST http://localhost:8429/snapshot/create

# List snapshots
curl http://localhost:8429/snapshot/list
```

### Restoring from Backup

```bash
# Restore from snapshot
kubectl exec -n monitoring vmsingle-pod -- /bin/sh -c 'cp -r /snapshot/* /victoria-metrics-data/'
```

## Migration Validation

### Metrics Comparison

1. Compare metric counts: `prometheus_tsdb_symbol_table_size_bytes` vs `vm_rows`
2. Verify all ServiceMonitors converted to VMServiceScrapes
3. Check all PrometheusRules converted to VMRules
4. Validate dashboard functionality with new datasource

### Performance Monitoring

Monitor the following metrics post-migration:
- Memory usage reduction
- Query performance improvement
- Storage efficiency gains
- Scrape success rates

## Support

For issues related to:
- **Victoria Metrics**: Check [official documentation](https://docs.victoriametrics.com/)
- **Kubernetes Integration**: Review operator logs and CRD status
- **Migration Problems**: Compare configurations between old and new stacks