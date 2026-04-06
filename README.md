# civilsnut-labbet

A production-ready Kubernetes homelab cluster running on Talos Linux, managed with FluxCD and automated dependency updates via Renovate.

## Cluster Architecture

- **Platform**: Talos Linux
- **CNI**: Cilium with Gateway API support and BGP peering
- **GitOps**: FluxCD
- **Certificate Management**: cert-manager with Let's Encrypt (Cloudflare DNS-01)
- **Storage**: Rook-Ceph
- **Monitoring**: Victoria Metrics + Grafana (with tsidp OIDC SSO)
- **Ingress**: Cilium Gateway API
- **Secret Management**: External Secrets Operator + 1Password Connect
- **Remote Access**: Tailscale Operator + subnet router

## Current Application Versions

### Foundation (00-foundation)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.18.4` | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | `v1.19.1` | TLS Certificate Management |
| **External Secrets** | `1.1.1` | Kubernetes Secret Management |
| **1Password Connect** | `2.0.5` | Secret Synchronization |
| **CoreDNS patch** | - | ts.net hostname resolution for OIDC |

### Infrastructure (01-infrastructure)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Rook-Ceph** | operator + cluster | Distributed Block Storage |
| **Shared Gateway** | - | Cilium Gateway API |
| **Tailscale Operator** | `1.94.2` | Tailscale Kubernetes Operator + subnet router |
| **tsidp** | `v0.0.9` | Tailscale OIDC Identity Provider |
| **External DNS** | - | Automatic DNS record management (Unifi) |

### Applications (02-applications)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Victoria Metrics** | `0.70.0` | Monitoring & Observability |
| **Grafana** | - | Dashboards with tsidp OIDC SSO |
| **Home Assistant** | `2026.2.3` | Home Automation Platform |
| **Zigbee2MQTT** | `2.9.1` | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `2.0.22` | MQTT Broker |

## Grafana Access

Grafana is available via the cluster's custom domain with automatic SSO via tsidp.

- On LAN: direct via Cilium gateway
- Remote: via Tailscale subnet router with split DNS
- Auth: tsidp OIDC (Tailscale identity provider)

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
