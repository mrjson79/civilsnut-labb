# civilsnut-labbet

A production-ready Kubernetes homelab cluster running on Talos Linux, managed with FluxCD and automated dependency updates via Renovate.

## 🏗️ Cluster Architecture

- **Platform**: Talos Linux
- **CNI**: Cilium with Gateway API support
- **GitOps**: FluxCD
- **Certificate Management**: cert-manager with Let's Encrypt
- **Storage**: Longhorn distributed storage
- **Monitoring**: Prometheus, Grafana, Alertmanager
- **Ingress**: Cilium Gateway API + NGINX Ingress Controller
- **Secret Management**: External Secrets Operator + 1Password Connect

## 📊 Current Application Versions

### Infrastructure Components
| Application | Version | Purpose |
|-------------|---------|---------|
| **Cilium** | `1.18.3` | CNI, Load Balancing, Gateway API |
| **cert-manager** | `v1.19.1` | TLS Certificate Management |
| **External Secrets** | `1.1.0` | Kubernetes Secret Management |
| **Ingress NGINX** | `4.14.0` | HTTP(S) Ingress Controller |
| **Longhorn** | `1.10.1` | Distributed Block Storage |
| **1Password Connect** | `2.0.5` | Secret Synchronization |

### Monitoring & Observability
| Application | Version | Purpose |
|-------------|---------|---------|
| **kube-prometheus-stack** | `79.7.1` | Monitoring Stack (Prometheus, Grafana, Alertmanager) |

### Home Automation & IoT
| Application | Version | Purpose |
|-------------|---------|---------|
| **Home Assistant** | `2025.11.3` | Home Automation Platform |
| **Zigbee2MQTT** | `2.6.3` | Zigbee to MQTT Bridge |
| **Mosquitto MQTT** | `latest` | MQTT Broker |


## 🔄 Automated Updates

- **Renovate** automatically creates PRs for dependency updates
- **Security updates** are prioritized and can be scheduled any time
- **Major updates** require manual review and approval
- **Digest updates** (container image updates) are auto-merged

## 📚 Documentation

- **FluxCD**: https://fluxcd.io/flux/
- **Cilium**: https://docs.cilium.io/
- **Talos**: https://www.talos.dev/
- **Gateway API**: https://gateway-api.sigs.k8s.io/

---

*Last updated: Managed automatically by Renovate*
