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

Chart versions unless noted; last synced with the manifests 2026-08-04.
See `fluxcd/README.md` for the detailed per-stack breakdown.

### Foundation (00-foundation)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.20.0` | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | `v1.21.1` | TLS Certificate Management |
| **External Secrets** | `2.8.0` | Kubernetes Secret Management |
| **1Password Connect** | `2.4.1` | Secret Synchronization |
| **Gateway API CRDs** | `v1.6.0` | Gateway API CRDs (experimental channel) |
| **Prometheus Operator CRDs** | `v0.92.1` | CRDs installed ahead of kube-prometheus-stack |
| **CoreDNS patch** | - | Corefile customizations (ts.net rewrite for OIDC) |

### Infrastructure (01-infrastructure)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Rook-Ceph** | `v1.20.3` (Ceph `v20.2.2`) | Distributed block storage + RGW object store |
| **Shared Gateway** | - | Cilium Gateway API gateway |
| **CloudNativePG** | `0.29.0` (operator `1.30.0`) | Postgres operator (zitadel-pg: 2 instances, WAL archiving + nightly backups to RGW) |
| **Zitadel** | `10.0.4` (app `v4.15.3`) | Self-hosted OIDC Identity Provider (idp.civilsnut.se) |
| **oauth2-proxy** | `10.7.0` (app `v7.15.3`) | ext_authz bridge for Gateway API ExternalAuth (GEP-1494) |
| **Tinkerbell** | `v0.23.0` | Bare-metal PXE provisioning of Flatcar nodes |

### Applications (02-applications)
| Application | Version | Purpose |
|-------------|---------|---------|
| **kube-prometheus-stack** | `88.0.1` | Prometheus, Alertmanager, Grafana (Zitadel OIDC SSO) |
| **Loki** | `7.2.0` | Log storage (queried from Grafana) |
| **Grafana Alloy** | `1.11.0` | Node agent shipping logs → Loki, node metrics → Prometheus |
| **InfluxDB2** | `2.1.2` | Time-series store for energy metrics |
| **signal-cli-rest-api** | `0.100` (image) | Signal Messenger delivery for critical Alertmanager alerts |
| **alertmanager-webhook-signal** | `1.1.1` (image) | Alertmanager → signal-cli-rest-api webhook translator |
| **Flux Web** | flux-operator `v0.57.0` | Flux Operator web UI (fluxcd.civilsnut.se) |
| **Home Assistant** | `2026.2.3` (image) | Home Automation Platform |
| **Zigbee2MQTT** | `2.12.1` | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `2.0.22` (image) | MQTT Broker |
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
