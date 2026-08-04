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
| **Cilium** | 1.20.0 | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | v1.21.1 | TLS certificates via Let's Encrypt (Cloudflare DNS-01) |
| **External Secrets** | 2.8.0 | Kubernetes secret management |
| **1Password Connect** | 2.4.1 | Secret synchronization from 1Password |
| **Gateway API CRDs** | v1.6.0 | Gateway API custom resource definitions (experimental channel) |
| **Prometheus Operator CRDs** | v0.92.1 | Prometheus Operator custom resource definitions |
| **CoreDNS** | — | Corefile customizations (ts.net rewrite for OIDC) |

### 01-infrastructure
Infrastructure services that build on the foundation.

| Component | Version | Purpose |
|-----------|---------|---------|
| **Rook-Ceph** | v1.20.3 | Distributed block storage (operator + cluster) |
| **Shared Gateway** | — | Cilium Gateway API gateway |
| **Zitadel** | 10.0.4 | Self-hosted OIDC identity provider (idp.civilsnut.se) |
| **oauth2-proxy** | 10.7.0 | ext_authz bridge: Gateway API ExternalAuth filter → Zitadel |
| **Tinkerbell** | v0.23.0 | Bare-metal PXE provisioning of Flatcar nodes |

### 02-applications
User-facing applications.

| Component | Version | Purpose |
|-----------|---------|---------|
| **Monitoring** | see below | Metrics, logs and dashboards |
| **Flux Web** | latest | Flux Operator web UI (fluxcd.civilsnut.se) |
| **Home Assistant** | 2026.2.3 | Home automation platform |
| **Mosquitto MQTT** | 2.0.22 | MQTT broker |
| **Zigbee2MQTT** | 2.12.1 | Zigbee to MQTT bridge |
| **httpbin** | — | Test / debug endpoint (httpbin.civilsnut.se) |

The **monitoring** stack bundles several Helm releases in the `monitoring` namespace:

| Chart | Version | Role |
|-------|---------|------|
| **kube-prometheus-stack** | 87.21.0 | Prometheus, Alertmanager, Grafana, kube-state-metrics, prometheus-operator |
| **Loki** | 7.2.0 | Log storage |
| **Grafana Alloy** | 1.11.0 | Node agent shipping logs → Loki and node metrics → Prometheus |
| **InfluxDB2** | 2.1.2 | Time-series store for energy metrics |

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
