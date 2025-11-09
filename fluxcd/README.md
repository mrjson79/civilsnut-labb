# FluxCD Infrastructure

This directory contains FluxCD manifests for managing core infrastructure applications on the Kubernetes cluster. This is a migration from ArgoCD to FluxCD for better GitOps workflow.

## Structure

Each application is organized in its own directory with the following pattern:

```
fluxcd/
├── cert-manager/
│   ├── namespace.yaml          # Namespace definition
│   ├── repository.yaml         # HelmRepository for chart source
│   ├── release.yaml           # HelmRelease for the application
│   ├── kustomization.yaml     # Kustomization for applying resources
│   └── manifests/             # Additional manifests (copied from ArgoCD)
├── ingress-nginx/
├── shared-gateway/
├── longhorn/
└── infrastructure.yaml        # Main kustomization that orchestrates everything
```

## Applications

### 1. cert-manager
- **Purpose**: Certificate management for TLS certificates
- **Chart**: jetstack/cert-manager v1.19.1
- **Dependencies**: None (base infrastructure)
- **Namespace**: cert-manager
- **Features**:
  - Wildcard certificate management
  - Cloudflare DNS challenge
  - Prometheus monitoring enabled

### 2. ingress-nginx
- **Purpose**: Ingress controller for HTTP/HTTPS traffic
- **Chart**: kubernetes/ingress-nginx v4.13.3
- **Dependencies**: cert-manager (for wildcard certificates)
- **Namespace**: ingress-nginx
- **Features**:
  - NodePort service (ports 30080/30443)
  - Automatic wildcard certificate usage
  - Resource limits for virtual nodes

### 3. shared-gateway
- **Purpose**: Gateway API resources for traffic routing
- **Type**: Pure manifests (no Helm chart)
- **Dependencies**: ingress-nginx
- **Namespace**: gateway-system
- **Features**:
  - Gateway API implementation
  - RBAC configurations
  - Reference grants for cross-namespace access

### 4. longhorn
- **Purpose**: Distributed block storage for persistent volumes
- **Chart**: longhorn/longhorn v1.10.0
- **Dependencies**: shared-gateway (for UI access)
- **Namespace**: longhorn-system
- **Features**:
  - Custom data path: /var/mnt/storage
  - Node selection: has-disk="yes"
  - UI access via Gateway API

## Deployment Order

The applications are deployed in the following order through FluxCD dependencies:

1. **cert-manager** (base dependency)
2. **cert-manager config** (depends on cert-manager release)
3. **ingress-nginx** (depends on cert-manager config)
4. **ingress-nginx config** (depends on ingress-nginx release)
5. **shared-gateway** (depends on ingress-nginx config)
6. **longhorn** (depends on cert-manager config, can run parallel with gateway)

## Usage

### Deploy All Infrastructure
```bash
# Apply the main infrastructure kustomization
kubectl apply -f infrastructure.yaml

# Or if using Flux CLI
flux create kustomization infrastructure \
  --source=flux-system \
  --path="./fluxcd"