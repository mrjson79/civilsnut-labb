# FluxCD GitOps

This directory contains FluxCD manifests for managing the Kubernetes cluster, organized in three deployment phases.

## Structure

```
fluxcd/
├── 00-foundation/          # Core platform components
│   ├── cert-manager/
│   ├── cilium/
│   ├── coredns/            # CoreDNS patches (ts.net rewrite for OIDC)
│   ├── external-secrets/
│   ├── gateway-api/
│   ├── onepassword-connect/
│   └── victoria-metrics-crds/
├── 01-infrastructure/      # Infrastructure services
│   ├── external-dns/
│   ├── rook-ceph/
│   ├── shared-gateway/
│   ├── tailscale/          # Operator + subnet router (192.168.4.0/24)
│   └── tsidp/              # Tailscale OIDC identity provider
└── 02-applications/        # User-facing applications
    ├── home-assistant/
    ├── mqtt/
    ├── vm-stack/           # Victoria Metrics + Grafana (tsidp OIDC SSO)
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
| **CoreDNS** | Patch to rewrite `idp.tail79231e.ts.net` → Tailscale egress proxy for OIDC |

### 01-infrastructure
Infrastructure services that build on the foundation.

| Component | Purpose |
|-----------|---------|
| **Rook-Ceph** | Distributed block storage |
| **Shared Gateway** | Cilium Gateway API gateway (192.168.4.10) |
| **Tailscale Operator** | Tailscale Kubernetes integration + subnet router |
| **tsidp** | Tailscale OIDC identity provider (`idp.tail79231e.ts.net`) |
| **External DNS** | Automatic DNS record management (Unifi webhook) |

### 02-applications
User-facing applications.

| Component | Purpose |
|-----------|---------|
| **Home Assistant** | Home automation platform |
| **Mosquitto MQTT** | MQTT broker |
| **Victoria Metrics Stack** | Monitoring + Grafana with tsidp OIDC SSO |
| **Zigbee2MQTT** | Zigbee to MQTT bridge |

## Grafana OIDC Architecture

Grafana uses tsidp for SSO. The token exchange flow requires the Grafana pod to reach `idp.tail79231e.ts.net` from inside the cluster:

1. CoreDNS rewrites `idp.tail79231e.ts.net` → Tailscale egress proxy (`ts-tsidp-q49tg.tailscale.svc.cluster.local`)
2. Egress proxy (created by Tailscale operator via `tailscale.com/tailnet-fqdn` annotation on the `tsidp` Service in `monitoring`) bridges cluster → tailnet
3. `auth_url` uses the public `ts.net` hostname (browser redirect), `token_url`/`api_url` use `idp.tail79231e.ts.net` (resolved via CoreDNS rewrite)

## Usage

```bash
# Check FluxCD reconciliation status
flux get kustomizations

# Force reconciliation
flux reconcile kustomization flux-system --with-source
```
