# Plan: Replace vm-stack with kube-prometheus-stack + Loki + Alloy

Replace the VictoriaMetrics stack (`02-applications/vm-stack/`) with:

| Component | Chart | Version | Role |
|---|---|---|---|
| kube-prometheus-stack | `prometheus-community/kube-prometheus-stack` | 87.8.0 | Metrics: Prometheus, Alertmanager, Grafana, kube-state-metrics, prometheus-operator |
| Loki | `grafana/loki` | 7.0.0 | Log storage (replaces VictoriaLogs) |
| Grafana Alloy | `grafana/alloy` | 1.10.0 | Node agent (DaemonSet) shipping **both** logs → Loki and node metrics → Prometheus (replaces vector + node-exporter) |

Everything stays in the `monitoring` namespace. Storage stays on `ceph-block`, all
stateful/heavy components keep the `has-disk: "yes"` nodeSelector.

**Not migrated:** metrics history (VM TSDB is incompatible with Prometheus TSDB) and
log history (VictoriaLogs → Loki). Grafana gets a fresh PVC (release name changes),
so manually created dashboards/preferences on the old PVC are lost — provisioned
dashboards/datasources come back via the sidecar.

## Target layout

```
02-applications/monitoring/
├── plan.md                              # this file
├── kustomization.yaml
├── namespace.yaml                       # moved from vm-stack (same labels incl. PSS privileged)
├── repositories.yaml                    # HelmRepository: prometheus-community + grafana
├── kube-prometheus-stack.yaml           # HelmRelease
├── loki.yaml                            # HelmRelease
├── alloy.yaml                           # HelmRelease (config inline in values)
├── grafana-oidc-externalsecret.yaml     # carried over unchanged from vm-stack
├── tsidp-egress-service.yaml            # carried over unchanged (Tailscale egress to idp.tail79231e.ts.net)
├── httproute.yaml                       # carried over, backend → kube-prometheus-stack-grafana:80
├── referencegrant.yaml                  # carried over unchanged
├── loki-datasource.yaml                 # ConfigMap grafana_datasource=1 (replaces vlogs-datasource)
├── configs/
│   ├── kustomization.yaml
│   ├── additional-scrape-configs.yaml   # carried over (cilium-agent-additional job)
│   ├── flux-podmonitor.yaml             # VMPodScrape → PodMonitor
│   └── kube-state-metrics-config.yaml   # carried over (Gateway API + Flux CRS metrics)
└── service-monitors/
    ├── kustomization.yaml
    ├── cilium-agent-podmonitor.yaml         # VMPodScrape  → PodMonitor
    ├── cilium-operator-podmonitor.yaml      # VMPodScrape  → PodMonitor
    ├── hubble-metrics-servicemonitor.yaml   # VMServiceScrape → ServiceMonitor
    ├── hubble-relay-servicemonitor.yaml     # VMServiceScrape → ServiceMonitor
    ├── gateway-api-servicemonitor.yaml      # VMServiceScrape → ServiceMonitor
    ├── cilium-gateway-prometheusrule.yaml   # VMRule → PrometheusRule (alerts)
    ├── cilium-gateway-recordingrules.yaml   # VMRule → PrometheusRule (recording)
    └── httproute-dashboard.yaml             # ConfigMap, carried over as-is
```

CRD conversions are mechanical: `operator.victoriametrics.com/v1beta1` →
`monitoring.coreos.com/v1`, `VMServiceScrape→ServiceMonitor` (`relabelConfigs→relabelings`
if any), `VMPodScrape→PodMonitor` (`podMetricsEndpoints` keeps its name),
`VMRule→PrometheusRule` (spec identical). Drop the
`release: victoria-metrics-k8s-stack` labels — Prometheus will be configured to
select **all** monitors/rules regardless of labels (see values below), matching the
current `selectAllByDefault: true` behavior.

## Changes outside `02-applications/monitoring/`

1. **`00-foundation/`**: add `prometheus-operator-crds/` mirroring the existing
   `victoria-metrics-crds/` pattern, so ServiceMonitor/PodMonitor/PrometheusRule CRDs
   exist for Flux server-side dry-run before the HelmRelease installs. Source:
   `https://github.com/prometheus-operator/prometheus-operator/releases/download/v0.85.0/stripped-down-crds.yaml`
   (match the operator version bundled in kube-prometheus-stack 87.8.0 — verify with
   `helm show chart`). After cutover is verified, remove `victoria-metrics-crds` from
   the foundation kustomization.
2. **`01-infrastructure/rook-ceph/vmservicescrape.yaml`** → `servicemonitor.yaml`
   (ServiceMonitor, same selector/endpoint, namespace `rook-ceph`).
3. **`02-applications/mqtt/manifests/vmservicescrape.yaml`** → `servicemonitor.yaml`
   (ServiceMonitor, namespace `mosquitto`).
4. **`02-applications/kustomization.yaml`**: `- vm-stack` → `- monitoring`.
5. **Delete `02-applications/vm-stack/`** entirely.

Because the VM operator runs with `disable_prometheus_converter: true`, steps 1–3 can
land **before** the cutover without the VM stack reacting to the new ServiceMonitors.

## HelmRelease values — key decisions

### kube-prometheus-stack

```yaml
# HelmRelease: kube-prometheus-stack, interval 5m, timeout 35m,
# install.createNamespace false (namespace.yaml owns it), retries 3, crds: CreateReplace
values:
  fullnameOverride: kube-prometheus-stack

  prometheus:
    prometheusSpec:
      # replaces selectAllByDefault: true — pick up ALL monitors/rules cluster-wide,
      # ignoring helm-release labels:
      serviceMonitorSelectorNilUsesHelmValues: false
      podMonitorSelectorNilUsesHelmValues: false
      ruleSelectorNilUsesHelmValues: false
      probeSelectorNilUsesHelmValues: false
      scrapeConfigSelectorNilUsesHelmValues: false
      scrapeInterval: 30s
      externalLabels:
        cluster: omni-cluster
      retention: 30d           # VM had retentionPeriod "10" (months); 30d is a deliberate cut,
      retentionSize: 45GB      # sized to the 50Gi PVC. Bump PVC+retention later if wanted.
      enableRemoteWriteReceiver: true   # Alloy pushes node metrics via remote_write
      additionalScrapeConfigsSecret:
        enabled: true
        name: additional-scrape-configs
        key: additional-scrape-configs.yaml
      storageSpec:
        volumeClaimTemplate:
          spec:
            storageClassName: ceph-block
            accessModes: [ReadWriteOnce]
            resources: { requests: { storage: 50Gi } }
      nodeSelector: { has-disk: "yes" }
      resources:
        requests: { memory: 2Gi, cpu: 1000m }
        limits:   { memory: 4Gi, cpu: 2000m }

  alertmanager:
    alertmanagerSpec:
      storage:
        volumeClaimTemplate:
          spec:
            storageClassName: ceph-block
            accessModes: [ReadWriteOnce]
            resources: { requests: { storage: 10Gi } }
      nodeSelector: { has-disk: "yes" }
      resources:
        requests: { memory: 256Mi, cpu: 100m }
        limits:   { memory: 512Mi, cpu: 200m }

  grafana:
    enabled: true
    deploymentStrategy: { type: Recreate }   # RWO PVC — old pod must die before new one mounts
    persistence:
      enabled: true
      storageClassName: ceph-block
      size: 10Gi
      accessModes: [ReadWriteOnce]
    envFromSecrets:
      - name: grafana-oidc
    grafana.ini:
      server:
        # Fixes "Grafana has failed to load its application files":
        # Grafana must know its public URL when behind the Gateway. We serve at the
        # domain ROOT (no subpath), so root_url carries no path and
        # serve_from_sub_path stays false. Do NOT set a subpath unless the
        # HTTPRoute starts routing a path prefix.
        root_url: https://grafana.civilsnut.se/
        serve_from_sub_path: false
      auth.generic_oauth:
        enabled: true
        name: Tailscale
        allow_sign_up: true
        auto_login: true
        client_id: $__env{GF_AUTH_GENERIC_OAUTH_CLIENT_ID}
        client_secret: $__env{GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET}
        scopes: openid email profile
        auth_url: https://idp.tail79231e.ts.net/authorize
        token_url: https://idp.tail79231e.ts.net/token
        api_url: https://idp.tail79231e.ts.net/userinfo
      auth.basic:
        enabled: false
    sidecar:
      dashboards:  { enabled: true }
      datasources: { enabled: true }
    nodeSelector: { has-disk: "yes" }
    resources:
      requests: { memory: 256Mi, cpu: 100m }
      limits:   { memory: 512Mi, cpu: 200m }

  nodeExporter:
    enabled: false   # Alloy's prometheus.exporter.unix replaces it (see alloy values)

  kubeStateMetrics: { enabled: true }
  kube-state-metrics:
    # CHANGE from vm-stack: run standard collectors AND the custom-resource-state
    # config. vm-stack ran --custom-resource-state-only with a gateway/flux-only
    # allowlist, which suppresses kube_pod_*/kube_deployment_* etc. — the
    # kube-prometheus-stack default rules and dashboards need those.
    extraArgs:
      - --custom-resource-state-config-file=/etc/customresourcestate/kube-state-metrics-config.yaml
    rbac:
      extraRules: []   # carry over the Gateway API + Flux list/watch rules verbatim from vm-stack
    volumeMounts:
      - name: flux-kube-state-metrics-config
        mountPath: /etc/customresourcestate
        readOnly: true
    volumes:
      - name: flux-kube-state-metrics-config
        configMap: { name: flux-kube-state-metrics-config }

  defaultRules:
    create: true
    # etcd/kubeScheduler/kubeControllerManager/kubeProxy rules+scrapes need review on
    # Talos: control-plane components don't expose metrics on hostNetwork by default.
    # Start with kubeControllerManager.enabled/kubeScheduler.enabled/kubeProxy.enabled/
    # kubeEtcd.enabled = false to avoid permanently-firing TargetDown alerts; enable
    # later if the endpoints are reachable.

  prometheusOperator:
    nodeSelector: { has-disk: "yes" }
```

### Loki (single-binary, filesystem on ceph-block — homelab-sized, mirrors vlogs)

```yaml
values:
  deploymentMode: SingleBinary
  loki:
    auth_enabled: false
    commonConfig: { replication_factor: 1 }
    storage: { type: filesystem }
    schemaConfig:
      configs:
        - from: "2026-01-01"
          store: tsdb
          object_store: filesystem
          schema: v13
          index: { prefix: index_, period: 24h }
    limits_config:
      retention_period: 168h        # 7d, matches vlogs retentionPeriod "7"
    compactor:
      retention_enabled: true
      delete_request_store: filesystem
  singleBinary:
    replicas: 1
    persistence:
      enabled: true
      storageClass: ceph-block
      size: 20Gi
    nodeSelector: { has-disk: "yes" }
    resources:
      requests: { memory: 1Gi, cpu: 250m }   # vlogs needed this after GC-thrashing at 512Mi
      limits:   { memory: 2Gi,  cpu: "1" }
  # zero out the scalable targets
  backend: { replicas: 0 }
  read:    { replicas: 0 }
  write:   { replicas: 0 }
  gateway: { enabled: false }       # Grafana/Alloy talk straight to loki:3100
  chunksCache:  { enabled: false }  # memcached overhead not worth it at this scale
  resultsCache: { enabled: false }
  lokiCanary: { enabled: false }
  test: { enabled: false }
  monitoring:
    serviceMonitor: { enabled: true }
```

Grafana datasource ConfigMap (`loki-datasource.yaml`, sidecar-provisioned):
`type: loki`, `url: http://loki.monitoring.svc:3100`. The
`victoriametrics-logs-datasource` plugin and vlogs dashboards are dropped.

### Alloy (DaemonSet — logs + node metrics from every node)

```yaml
values:
  controller:
    type: daemonset
    tolerations:
      - operator: Exists            # run on all nodes incl. control-plane
  alloy:
    clustering: { enabled: false }
    mounts: { varlog: true }        # /var/log for pod logs
    configMap:
      create: true
      content: |
        // ---- LOGS: all pod logs on this node -> Loki ----
        discovery.kubernetes "pods" {
          role = "pod"
          selectors {
            role  = "pod"
            field = "spec.nodeName=" + sys.env("HOSTNAME_NODE")
          }
        }
        discovery.relabel "pods" {
          targets = discovery.kubernetes.pods.targets
          rule { source_labels = ["__meta_kubernetes_namespace"],       target_label = "namespace" }
          rule { source_labels = ["__meta_kubernetes_pod_name"],        target_label = "pod" }
          rule { source_labels = ["__meta_kubernetes_pod_container_name"], target_label = "container" }
          rule { source_labels = ["__meta_kubernetes_pod_node_name"],   target_label = "node" }
        }
        loki.source.kubernetes "pods" {
          targets    = discovery.relabel.pods.output
          forward_to = [loki.write.default.receiver]
        }
        loki.write "default" {
          endpoint { url = "http://loki.monitoring.svc:3100/loki/api/v1/push" }
          external_labels = { cluster = "omni-cluster" }
        }

        // ---- METRICS: embedded node_exporter -> Prometheus remote_write ----
        prometheus.exporter.unix "node" { }
        prometheus.scrape "node" {
          targets         = prometheus.exporter.unix.node.targets
          scrape_interval = "30s"
          forward_to      = [prometheus.relabel.node.receiver]
        }
        prometheus.relabel "node" {
          // keep job/instance compatible with kube-prometheus-stack's
          // node-exporter dashboards and recording rules
          rule { target_label = "job",      replacement = "node-exporter" }
          rule { target_label = "instance", replacement = sys.env("HOSTNAME_NODE") }
          forward_to = [prometheus.remote_write.default.receiver]
        }
        prometheus.remote_write "default" {
          endpoint { url = "http://kube-prometheus-stack-prometheus.monitoring.svc:9090/api/v1/write" }
        }
    extraEnv:
      - name: HOSTNAME_NODE
        valueFrom: { fieldRef: { fieldPath: spec.nodeName } }
    resources:
      requests: { memory: 128Mi, cpu: 50m }
      limits:   { memory: 384Mi, cpu: 200m }
  serviceMonitor: { enabled: true }
```

Notes on this choice (per request, Alloy is the node agent for both signals):

- Prometheus does **not** scrape node metrics; Alloy pushes them via remote_write,
  hence `enableRemoteWriteReceiver: true` on Prometheus. The relabel to
  `job="node-exporter"` keeps the bundled node dashboards/rules working.
- `loki.source.kubernetes` tails logs via the kubelet API — no hostPath log parsing
  format worries, works with Talos. Alloy needs RBAC for pods (`get/list/watch`) and
  `nodes/proxy`; the chart's default ClusterRole covers this.
- Talos runs no journald persistence for host logs by default; pod logs are the
  scope here (same as vector before). Kernel/kubelet metrics beyond node_exporter
  still come from the kubelet ServiceMonitor bundled with kube-prometheus-stack.

## Migration sequence (per commit)

1. **Commit 1 — CRDs + monitor conversions (safe, no behavior change):**
   - Add `00-foundation/prometheus-operator-crds/`.
   - Convert rook-ceph and mqtt VMServiceScrapes to ServiceMonitors.
   - VM operator ignores ServiceMonitors (converter disabled) → nothing changes yet.
2. **Commit 2 — cutover:**
   - Add `02-applications/monitoring/` (everything above; `namespace.yaml`,
     ExternalSecret, tsidp egress Service, ReferenceGrant, HTTPRoute moved over —
     HTTPRoute backend renamed to `kube-prometheus-stack-grafana`).
   - Swap `- vm-stack` → `- monitoring` in `02-applications/kustomization.yaml`.
   - Delete `02-applications/vm-stack/`. Flux prunes the old HelmReleases; the
     namespace, secret, egress service, ReferenceGrant survive because the new
     kustomization now owns identical objects.
3. **Commit 3 — cleanup (after verification):**
   - Remove `00-foundation/victoria-metrics-crds/` and its kustomization entry.
   - Manually delete leftover PVCs (operator-created, not Helm-owned):
     `vmsingle-*`, `vmalertmanager-*`, `victoria-logs-*`, and the old
     `victoria-metrics-k8s-stack-grafana` PVC.
   - `kubectl delete crd` for the `operator.victoriametrics.com` group once nothing
     references it.

## Verification checklist

- `kustomize build fluxcd/02-applications` renders clean; `flux get hr -n monitoring`
  all Ready.
- Prometheus targets page: kubelet, apiserver, kube-state-metrics, cilium
  (agent/operator/hubble), gateway-api, flux PodMonitor, rook-ceph-mgr, mosquitto,
  loki, alloy — all up. `node-exporter` job present **via remote_write** (check
  `up{job="node-exporter"}` absent but `node_cpu_seconds_total{job="node-exporter"}`
  present — remote_write carries no `up` metric; the Alloy ServiceMonitor +
  `alloy_component_controller_running_components` covers agent liveness).
- Loki: `logcli`/Grafana Explore query `{namespace="monitoring"}` returns fresh lines
  from every node's pods.
- Grafana at https://grafana.civilsnut.se loads (no "failed to load application
  files"), Tailscale OIDC auto-login works (tsidp egress Service + CoreDNS ts.net
  rewrite must remain intact), Loki + Prometheus datasources healthy, node/cluster/
  httproute dashboards render.
- Alertmanager reachable from Prometheus; Watchdog alert firing (always-on canary);
  no stuck TargetDown for disabled control-plane scrapes.

## Open items / risks

- **kube-state-metrics behavior change** (standard collectors re-enabled, allowlist
  dropped) — intended, but watch cardinality.
- **defaultRules for etcd/scheduler/controller-manager/kube-proxy on Talos** — start
  disabled, enable selectively after checking endpoint reachability.
- **Retention semantics changed**: VM stored ~10 months; Prometheus plan is
  30d/45GB. Adjust `retention`/PVC if longer history is wanted.
- **prometheus-operator CRD version in foundation** must match chart 87.8.0's
  bundled operator; verify exact tag before commit 1.
- Grafana alert history/manual dashboards on the old PVC are not carried over.
