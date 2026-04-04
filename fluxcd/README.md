# FluxCD GitOps

This directory contains FluxCD manifests for managing the Kubernetes cluster, organized in three deployment phases.

## Structure

```
fluxcd/
├── 00-foundation/          # Core platform components
│   ├── cert-manager/
│   ├── cilium/
│   ├── external-secrets/
│   ├── gateway-api/
│   ├── onepassword-connect/
│   └── victoria-metrics-crds/
├── 01-infrastructure/      # Infrastructure services
│   ├── external-dns/
│   ├── rook-ceph/
│   ├── shared-gateway/
│   ├── tailscale/
│   └── tsidp/
└── 02-applications/        # User-facing applications
    ├── home-assistant/
    ├── mqtt/
    ├── vm-stack/
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

| Component | Purpose |
|-----------|---------|
| **Cilium** | CNI, Load Balancing, Gateway API, BGP |
| **cert-manager** | TLS certificates via Let's Encrypt (Cloudflare DNS-01) |
| **External Secrets** | Kubernetes secret management |
| **1Password Connect** | Secret synchronization from 1Password |
| **Gateway API CRDs** | Gateway API custom resource definitions |
| **Victoria Metrics CRDs** | Victoria Metrics custom resource definitions |

### 01-infrastructure
Infrastructure services that build on the foundation.

| Component | Purpose |
|-----------|---------|
| **Rook-Ceph** | Distributed block storage |
| **Shared Gateway** | Cilium Gateway API gateway |
| **Tailscale Operator** | Tailscale Kubernetes integration |
| **tsidp** | Tailscale identity provider |
| **External DNS** | Automatic DNS record management |

### 02-applications
User-facing applications.

| Component | Purpose |
|-----------|---------|
| **Home Assistant** | Home automation platform |
| **Mosquitto MQTT** | MQTT broker |
| **Victoria Metrics Stack** | Monitoring and observability |
| **Zigbee2MQTT** | Zigbee to MQTT bridge |

## Usage

```bash
# Check FluxCD reconciliation status
flux get kustomizations

# Force reconciliation
flux reconcile kustomization flux-system --with-source
```
