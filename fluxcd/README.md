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
│   ├── tailscale/          # Operator + subnet router
│   ├── zitadel/            # Self-hosted OIDC identity provider
│   └── oauth2-proxy/       # ext-auth bridge for Gateway API ExternalAuth
└── 02-applications/        # User-facing applications
    ├── home-assistant/
    ├── mqtt/
    ├── vm-stack/           # Victoria Metrics + Grafana (Zitadel OIDC SSO)
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
| **CoreDNS** | Corefile customizations |

### 01-infrastructure
Infrastructure services that build on the foundation.

| Component | Purpose |
|-----------|---------|
| **Rook-Ceph** | Distributed block storage |
| **Shared Gateway** | Cilium Gateway API gateway |
| **Tailscale Operator** | Tailscale Kubernetes integration + subnet router |
| **Zitadel** | Self-hosted OIDC identity provider (idp.civilsnut.se) |
| **oauth2-proxy** | ext_authz bridge: Gateway API ExternalAuth filter → Zitadel |
| **External DNS** | Automatic DNS record management (Unifi webhook) |

### 02-applications
User-facing applications.

| Component | Purpose |
|-----------|---------|
| **Home Assistant** | Home automation platform |
| **Mosquitto MQTT** | MQTT broker |
| **Victoria Metrics Stack** | Monitoring + Grafana with Zitadel OIDC SSO |
| **Zigbee2MQTT** | Zigbee to MQTT bridge |

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
