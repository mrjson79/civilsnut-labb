# civilsnut-labbet

A production-ready Kubernetes homelab cluster running on Talos Linux, managed with FluxCD and automated dependency updates via Renovate.

## Cluster Architecture

- **Platform**: Talos Linux
- **CNI**: Cilium with Gateway API support and BGP peering
- **GitOps**: FluxCD
- **Certificate Management**: cert-manager with Let's Encrypt (Cloudflare DNS-01)
- **Storage**: Rook-Ceph
- **Monitoring**: Victoria Metrics + Grafana
- **Ingress**: Cilium Gateway API + NGINX Ingress Controller
- **Secret Management**: External Secrets Operator + 1Password Connect

## Current Application Versions

### Foundation (00-foundation)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.18.4` | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | `v1.19.1` | TLS Certificate Management |
| **External Secrets** | `1.1.1` | Kubernetes Secret Management |
| **1Password Connect** | `2.0.5` | Secret Synchronization |

### Infrastructure (01-infrastructure)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Rook-Ceph** | operator + cluster | Distributed Block Storage |
| **Shared Gateway** | - | Cilium Gateway API (192.168.4.10) |

### Applications (02-applications)
| Application | Version | Purpose |
|-------------|---------|---------|
| **Victoria Metrics** | `0.70.0` | Monitoring & Observability |
| **Ingress NGINX** | `4.14.1` | HTTP(S) Ingress Controller |
| **Home Assistant** | `2026.2.3` | Home Automation Platform |
| **Zigbee2MQTT** | `2.9.1` | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `2.0.22` | MQTT Broker |

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
