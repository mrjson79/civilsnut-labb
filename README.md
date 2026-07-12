# civilsnut-labbet

A production-ready Kubernetes homelab cluster running on Talos Linux, managed with FluxCD and automated dependency updates via Renovate.

## Cluster Architecture

- **Platform**: Talos Linux
- **CNI**: Cilium with Gateway API support and BGP peering
- **GitOps**: FluxCD
- **Certificate Management**: cert-manager with Let's Encrypt (Cloudflare DNS-01)
- **Storage**: Rook-Ceph
- **Monitoring**: Victoria Metrics + Grafana (with Zitadel OIDC SSO)
- **Identity**: Zitadel (self-hosted OIDC) + oauth2-proxy (Gateway API ExternalAuth)
- **Ingress**: Cilium Gateway API
- **Secret Management**: External Secrets Operator + 1Password Connect

## Current Application Versions

### Foundation (00-foundation)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.20.0-pre.4` | CNI, Load Balancing, Gateway API (v1.6.0 experimental), BGP |
| **cert-manager** | `v1.19.1` | TLS Certificate Management |
| **External Secrets** | `1.1.1` | Kubernetes Secret Management |
| **1Password Connect** | `2.0.5` | Secret Synchronization |
| **CoreDNS patch** | - | Corefile customizations |

### Infrastructure (01-infrastructure)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Rook-Ceph** | operator + cluster | Distributed Block Storage |
| **Shared Gateway** | - | Cilium Gateway API |
| **Zitadel** | `v4.15.3` | Self-hosted OIDC Identity Provider (idp.civilsnut.se) |
| **oauth2-proxy** | `7.15.3` | ext_authz bridge for Gateway API ExternalAuth (GEP-1494) |
| **External DNS** | - | Automatic DNS record management (Unifi) |

### Applications (02-applications)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Victoria Metrics** | `0.70.0` | Monitoring & Observability |
| **Grafana** | - | Dashboards with Zitadel OIDC SSO |
| **Home Assistant** | `2026.2.3` | Home Automation Platform |
| **Zigbee2MQTT** | `2.9.1` | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `2.0.22` | MQTT Broker |

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
