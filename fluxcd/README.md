# FluxCD GitOps

This directory contains FluxCD manifests for managing the Kubernetes cluster, organized in three deployment phases.

## Structure

```
fluxcd/
├── 00-foundation/              # Core platform components
│   ├── cert-manager/
│   ├── cilium/
│   ├── coredns/                # CoreDNS patches (ts.net rewrite for OIDC)
│   ├── external-secrets/
│   ├── gateway-api/            # Gateway API CRDs (experimental channel)
│   ├── onepassword-connect/
│   └── prometheus-operator-crds/
├── 01-infrastructure/          # Infrastructure services
│   ├── oauth2-proxy/           # ext-auth bridge for Gateway API ExternalAuth
│   ├── rook-ceph/
│   ├── shared-gateway/
│   ├── tinkerbell/             # Bare-metal PXE provisioning (Flatcar)
│   └── zitadel/                # Self-hosted OIDC identity provider
└── 02-applications/            # User-facing applications
    ├── flux-web/               # Flux Operator web UI (Zitadel OIDC SSO)
    ├── home-assistant/
    ├── httpbin/                # Test / debug endpoint
    ├── monitoring/             # kube-prometheus-stack + Loki + Alloy + InfluxDB
    ├── mqtt/
    └── zigbee2mqtt/
```

Each application follows a common pattern:

```
application/
├── namespace.yaml
├── repository.yaml         # HelmRepository (if Helm-based)
├── release.yaml            # HelmRelease (if Helm-based)
├── kustomization.yaml      # Kustomization for applying resources
└── manifests/              # Additional raw manifests
```

## Deployment Phases

### 00-foundation
Core platform components that everything else depends on.

| Component | Version | Purpose |
|-----------|---------|---------|
| **Cilium** | 1.20.1 <!-- renovate: datasource=helm depName=cilium registryUrl=https://helm.cilium.io --> | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | v1.21.1 <!-- renovate: datasource=helm depName=cert-manager registryUrl=https://charts.jetstack.io --> | TLS certificates via Let's Encrypt (Cloudflare DNS-01) |
| **External Secrets** | 2.9.0 <!-- renovate: datasource=helm depName=external-secrets registryUrl=https://charts.external-secrets.io --> | Kubernetes secret management |
| **1Password Connect** | 2.4.1 <!-- renovate: datasource=helm depName=connect registryUrl=https://1password.github.io/connect-helm-charts --> | Secret synchronization from 1Password |
| **Gateway API CRDs** | v1.6.0 | Gateway API custom resource definitions (experimental channel, vendored manifest) |
| **Prometheus Operator CRDs** | v0.93.1 <!-- renovate: datasource=github-releases depName=prometheus-operator/prometheus-operator --> | Prometheus Operator custom resource definitions |
| **CoreDNS** | — | Corefile customizations (ts.net rewrite for OIDC) |

### 01-infrastructure
Infrastructure services that build on the foundation.

| Component | Version | Purpose |
|-----------|---------|---------|
| **Rook-Ceph** | v1.20.3 <!-- renovate: datasource=helm depName=rook-ceph registryUrl=https://charts.rook.io/release --> | Distributed block storage (operator + cluster) |
| **Shared Gateway** | — | Cilium Gateway API gateway |
| **CloudNativePG** | 0.29.0 <!-- renovate: datasource=helm depName=cloudnative-pg registryUrl=https://cloudnative-pg.github.io/charts --> | Postgres operator (zitadel-pg) |
| **Zitadel** | 10.0.4 <!-- renovate: datasource=helm depName=zitadel registryUrl=https://charts.zitadel.com --> | Self-hosted OIDC identity provider (idp.civilsnut.se) |
| **oauth2-proxy** | 10.7.0 <!-- renovate: datasource=helm depName=oauth2-proxy registryUrl=https://oauth2-proxy.github.io/manifests --> | ext_authz bridge: Gateway API ExternalAuth filter → Zitadel |
| **Tinkerbell** | v0.23.0 <!-- renovate: datasource=docker depName=ghcr.io/tinkerbell/charts/tinkerbell --> | Bare-metal PXE provisioning of Flatcar nodes |

### 02-applications
User-facing applications.

| Component | Version | Purpose |
|-----------|---------|---------|
| **Monitoring** | see below | Metrics, logs and dashboards |
| **Flux Web** | — | Flux Operator web UI (fluxcd.civilsnut.se); image managed by flux-operator |
| **Home Assistant** | 2026.2.3 <!-- renovate: datasource=docker depName=ghcr.io/home-assistant/home-assistant --> | Home automation platform |
| **Fellow Aiden** | v1.3.3 <!-- renovate: datasource=github-releases depName=kristofferR/FellowAiden-HomeAssistant --> | HA custom component for the Fellow Aiden coffee brewer (init container) |
| **Immich** | 0.12.0 <!-- renovate: datasource=helm depName=immich registryUrl=https://immich-app.github.io/immich-charts --> / v3.0.3 <!-- renovate: datasource=docker depName=ghcr.io/immich-app/immich-server --> (image) | Self-hosted photo library (photos.civilsnut.se); CNPG cluster `immich-pg` on a VectorChord image |
| **Immich Kiosk** | 0.42.0 <!-- renovate: datasource=docker depName=ghcr.io/damongolding/immich-kiosk --> | Fullscreen slideshow over the Immich API (frame.civilsnut.se), iframed by the HA Family dashboard |
| **Mosquitto MQTT** | 2.0.22 <!-- renovate: datasource=docker depName=eclipse-mosquitto --> | MQTT broker |
| **Zigbee2MQTT** | 2.13.0 <!-- renovate: datasource=helm depName=zigbee2mqtt registryUrl=https://charts.zigbee2mqtt.io --> | Zigbee to MQTT bridge |
| **httpbin** | — | Test / debug endpoint (httpbin.civilsnut.se) |

The **monitoring** stack bundles several Helm releases in the `monitoring` namespace:

| Chart | Version | Role |
|-------|---------|------|
| **kube-prometheus-stack** | 88.3.0 <!-- renovate: datasource=helm depName=kube-prometheus-stack registryUrl=https://prometheus-community.github.io/helm-charts --> | Prometheus, Alertmanager, Grafana, kube-state-metrics, prometheus-operator |
| **Loki** | 7.3.0 <!-- renovate: datasource=helm depName=loki registryUrl=https://grafana.github.io/helm-charts --> | Log storage |
| **Grafana Alloy** | 1.11.1 <!-- renovate: datasource=helm depName=alloy registryUrl=https://grafana.github.io/helm-charts --> | Node agent shipping logs → Loki and node metrics → Prometheus |
| **InfluxDB2** | 2.1.2 <!-- renovate: datasource=helm depName=influxdb2 registryUrl=https://helm.influxdata.com --> | Time-series store for energy metrics |

### Alerting → Signal Messenger

Alertmanager routes `severity=critical` alerts to Signal (Note-to-Self on the
linked account); everything else stays null-routed, Watchdog is muted:

```
Prometheus rules → Alertmanager → signal-relay (webhook translator)
                                → signal-api (signal-cli-rest-api) → Signal
```

- `signal-api.yaml` — `bbernhard/signal-cli-rest-api` in `json-rpc` mode; the
  Signal device link lives on the `signal-cli-data` PVC (deleting it means
  re-linking via `/v1/qrcodelink`, which requires temporarily setting
  `MODE=normal`).
- `signal-relay.yaml` — `schlauerlauer/alertmanager-webhook-signal`; its
  config (phone numbers) is rendered from the 1Password `signal-relay` item
  by `signal-relay-externalsecret.yaml`.
- Routing/receivers: `alertmanager.config` in `kube-prometheus-stack.yaml`
  (note: setting `config` replaces the chart default wholesale, incl.
  inhibit rules).

## SSO Architecture (Zitadel)

Zitadel at `idp.civilsnut.se` (behind the shared gateway) is the OIDC provider
for everything:

- **Apps with native OIDC** (Grafana, Flux Web) are confidential clients of
  the Zitadel `homelab` project. Grafana's userinfo endpoint is
  `/oidc/v1/userinfo` (not `/oauth/v2/`).
- **Apps without auth** (Hubble UI, Zigbee2MQTT) are protected at the gateway
  with the Gateway API `ExternalAuth` HTTPRoute filter (experimental,
  GEP-1494) pointing at oauth2-proxy: proxy mode, `upstream: static://200`,
  wildcard `.civilsnut.se` session cookie. Each protected HTTPRoute carries a
  filterless `/oauth2` rule for the sign-in/callback endpoints, and each
  protected host is a redirect URI on the `oauth2-proxy` Zitadel app.
- Logins require a user grant on the `homelab` project (authorization check
  is enabled on the project).

## Usage

```bash
# Check FluxCD reconciliation status
flux get kustomizations

# Force reconciliation
flux reconcile kustomization flux-system --with-source
```
