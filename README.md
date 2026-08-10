# civilsnut-labbet

A production-ready Kubernetes homelab cluster running on Talos Linux, managed with FluxCD and automated dependency updates via Renovate.

## Cluster Architecture

- **Platform**: Talos Linux
- **CNI**: Cilium with Gateway API support and BGP peering
- **GitOps**: FluxCD
- **Certificate Management**: cert-manager with Let's Encrypt (Cloudflare DNS-01)
- **Storage**: Rook-Ceph
- **Monitoring**: kube-prometheus-stack (Prometheus, Alertmanager, Grafana) + Loki + Alloy; critical alerts to Signal Messenger
- **Identity**: Zitadel (self-hosted OIDC) + oauth2-proxy (Gateway API ExternalAuth)
- **Ingress**: Cilium Gateway API
- **Secret Management**: External Secrets Operator + 1Password Connect
- **Bare-metal provisioning**: Tinkerbell (PXE → Flatcar)

## Current Application Versions

Chart versions unless noted (image). Kept current by Renovate via the
docs-version-tables custom manager in `renovate.json` — version bumps here ride
in the same PR as the manifest change. See `fluxcd/README.md` for the detailed
per-stack breakdown.

### Foundation (00-foundation)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.20.0` <!-- renovate: datasource=helm depName=cilium registryUrl=https://helm.cilium.io --> | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | `v1.21.1` <!-- renovate: datasource=helm depName=cert-manager registryUrl=https://charts.jetstack.io --> | TLS Certificate Management |
| **External Secrets** | `2.8.0` <!-- renovate: datasource=helm depName=external-secrets registryUrl=https://charts.external-secrets.io --> | Kubernetes Secret Management |
| **1Password Connect** | `2.4.1` <!-- renovate: datasource=helm depName=connect registryUrl=https://1password.github.io/connect-helm-charts --> | Secret Synchronization |
| **Gateway API CRDs** | `v1.6.0` | Gateway API CRDs (experimental channel, vendored manifest) |
| **Prometheus Operator CRDs** | `v0.93.0` <!-- renovate: datasource=github-releases depName=prometheus-operator/prometheus-operator --> | CRDs installed ahead of kube-prometheus-stack |
| **CoreDNS patch** | - | Corefile customizations (ts.net rewrite for OIDC) |

### Infrastructure (01-infrastructure)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Rook-Ceph** | `v1.20.3` <!-- renovate: datasource=helm depName=rook-ceph registryUrl=https://charts.rook.io/release --> (Ceph `v20.2.2`) | Distributed block storage + RGW object store |
| **Shared Gateway** | - | Cilium Gateway API gateway |
| **CloudNativePG** | `0.29.0` <!-- renovate: datasource=helm depName=cloudnative-pg registryUrl=https://cloudnative-pg.github.io/charts --> | Postgres operator (zitadel-pg: 2 instances, WAL archiving + nightly backups to RGW) |
| **Zitadel** | `10.0.4` <!-- renovate: datasource=helm depName=zitadel registryUrl=https://charts.zitadel.com --> | Self-hosted OIDC Identity Provider (idp.civilsnut.se) |
| **oauth2-proxy** | `10.7.0` <!-- renovate: datasource=helm depName=oauth2-proxy registryUrl=https://oauth2-proxy.github.io/manifests --> | ext_authz bridge for Gateway API ExternalAuth (GEP-1494) |
| **Tinkerbell** | `v0.23.0` <!-- renovate: datasource=docker depName=ghcr.io/tinkerbell/charts/tinkerbell --> | Bare-metal PXE provisioning of Flatcar nodes |

### Applications (02-applications)
| Application | Version | Purpose |
|-------------|---------|---------|
| **kube-prometheus-stack** | `88.1.5` <!-- renovate: datasource=helm depName=kube-prometheus-stack registryUrl=https://prometheus-community.github.io/helm-charts --> | Prometheus, Alertmanager, Grafana (Zitadel OIDC SSO) |
| **Loki** | `7.2.0` <!-- renovate: datasource=helm depName=loki registryUrl=https://grafana.github.io/helm-charts --> | Log storage (queried from Grafana) |
| **Grafana Alloy** | `1.11.1` <!-- renovate: datasource=helm depName=alloy registryUrl=https://grafana.github.io/helm-charts --> | Node agent shipping logs → Loki, node metrics → Prometheus |
| **InfluxDB2** | `2.1.2` <!-- renovate: datasource=helm depName=influxdb2 registryUrl=https://helm.influxdata.com --> | Time-series store for energy metrics |
| **signal-cli-rest-api** | `0.100` <!-- renovate: datasource=docker depName=bbernhard/signal-cli-rest-api --> (image) | Signal Messenger delivery for critical Alertmanager alerts |
| **alertmanager-webhook-signal** | `1.1.1` <!-- renovate: datasource=docker depName=docker.io/schlauerlauer/alertmanager-webhook-signal --> (image) | Alertmanager → signal-cli-rest-api webhook translator |
| **Flux Web** | - | Flux Operator web UI (fluxcd.civilsnut.se); image managed by flux-operator |
| **Home Assistant** | `2026.2.3` <!-- renovate: datasource=docker depName=ghcr.io/home-assistant/home-assistant --> (image) | Home Automation Platform |
| **Fellow Aiden** | `v1.3.3` <!-- renovate: datasource=github-releases depName=kristofferR/FellowAiden-HomeAssistant --> (HA custom component) | Fellow Aiden coffee brewer integration |
| **iCloud Photos** | `1.29-alpine` <!-- renovate: datasource=docker depName=nginx --> / `3.13-alpine` <!-- renovate: datasource=docker depName=python --> (images) | Shared iCloud album mirror + slideshow (photos.civilsnut.se), embedded in the HA Family dashboard |
| **Zigbee2MQTT** | `2.13.0` <!-- renovate: datasource=helm depName=zigbee2mqtt registryUrl=https://charts.zigbee2mqtt.io --> | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `2.0.22` <!-- renovate: datasource=docker depName=eclipse-mosquitto --> (image) | MQTT Broker |
| **httpbin** | - | Test / debug endpoint |

## Grafana Access

Grafana is available via the cluster's custom domain with automatic SSO via Zitadel.

- On LAN: direct via Cilium gateway
- Auth: Zitadel OIDC (idp.civilsnut.se); apps without native auth
  (Hubble UI, Zigbee2MQTT) are protected at the gateway via the
  ExternalAuth HTTPRoute filter + oauth2-proxy

## Automated Updates

- **Renovate** automatically creates PRs for dependency updates
- **Security updates** are prioritized and can be scheduled any time
- **Major updates** require manual review and approval
- **Digest updates** (container image updates) are auto-merged

## Documentation

- **FluxCD**: https://fluxcd.io/flux/
- **Cilium**: https://docs.cilium.io/
- **Talos**: https://www.talos.dev/
- **Gateway API**: https://gateway-api.sigs.k8s.io/
