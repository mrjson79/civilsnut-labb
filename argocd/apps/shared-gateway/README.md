# Shared Gateway

This directory contains the configuration for a centralized, secure shared Gateway API gateway that can be used by multiple services across different namespaces.

## Overview

The shared gateway provides a centralized ingress solution using Kubernetes Gateway API with enhanced security controls. Instead of creating individual Gateway objects for each service, multiple services can share this single gateway while maintaining proper isolation and security.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     gateway-system namespace                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  Shared Gateway                             │ │
│  │  - Port 80 (HTTP)                                          │ │
│  │  - Port 443 (HTTPS with TLS termination)                  │ │
│  │  - Namespace selector for security                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ Routes traffic to
                                ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   podinfo ns    │  │  monitoring ns  │  │   your-app ns   │
│                 │  │                 │  │                 │
│  HTTPRoute ────▶│  │  HTTPRoute ────▶│  │  HTTPRoute ────▶│
│  Service        │  │  Service        │  │  Service        │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Components

### 1. Namespace (`namespace.yaml`)
- Creates `gateway-system` namespace
- Includes security labels and annotations

### 2. Gateway (`gateway.yaml`)
- Centralized Gateway with enhanced security
- HTTP (port 80) and HTTPS (port 443) listeners
- Namespace selector for access control
- TLS termination using wildcard certificate

### 3. ReferenceGrant (`referencegrant.yaml`)
- Allows Gateway to access TLS certificates from `ingress-nginx` namespace
- Maintains security boundaries

### 4. RBAC (`rbac.yaml`)
- ServiceAccount, ClusterRole, and bindings
- Proper permissions for gateway management
- Least-privilege access

## Security Features

### Namespace-Based Access Control
Only namespaces with the label `gateway.networking.k8s.io/allowed: "true"` can create HTTPRoutes that reference this gateway.

### TLS Certificate Management
- Uses existing wildcard certificate (`civilsnut-se-wildcard-tls`) from cert-manager namespace
- Direct access to cert-manager eliminates need for certificate copying
- ReferenceGrant ensures secure cross-namespace access
- No dependency on ingress-nginx for certificate distribution

### RBAC Controls
- Dedicated ServiceAccount with minimal required permissions
- Separate cluster and namespace-level roles
- Audit trail through ArgoCD annotations

## Usage

### Step 1: Enable Namespace Access
Label your namespace to allow access to the shared gateway:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: your-app-namespace
  labels:
    gateway.networking.k8s.io/allowed: "true"
```

### Step 2: Create HTTPRoute
Create an HTTPRoute in your application namespace:

```yaml
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: your-app
  namespace: your-app-namespace
spec:
  hostnames:
  - your-app.civilsnut.se
  parentRefs:
  - name: shared-gateway
    namespace: gateway-system
  rules:
  - backendRefs:
    - name: your-app-service
      port: 8080
    matches:
    - path:
        type: PathPrefix
        value: /
```

### Step 3: Create ReferenceGrant (if needed)
If your HTTPRoute is in a different namespace than the gateway:

```yaml
---
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-httproute-to-shared-gateway
  namespace: gateway-system
spec:
  from:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    namespace: your-app-namespace
  to:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: shared-gateway
```

## Migration from Individual Gateways

If you're migrating from individual Gateway objects:

### Before (Individual Gateway)
```yaml
# gateway.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: my-app-gateway
  namespace: my-app
spec:
  gatewayClassName: cilium
  listeners:
  - hostname: my-app.civilsnut.se
    name: http
    port: 80
    protocol: HTTP

---
# httproute.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app
  namespace: my-app
spec:
  parentRefs:
  - name: my-app-gateway  # References local gateway
  rules:
  - backendRefs:
    - name: my-app-service
      port: 8080
```

### After (Shared Gateway)
```yaml
# Only need HTTPRoute now
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app
  namespace: my-app
spec:
  hostnames:
  - my-app.civilsnut.se
  parentRefs:
  - name: shared-gateway
    namespace: gateway-system  # References shared gateway
  rules:
  - backendRefs:
    - name: my-app-service
      port: 8080
```

## Examples

### Simple Web Application
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: webapp
  namespace: webapp
spec:
  hostnames:
  - webapp.civilsnut.se
  parentRefs:
  - name: shared-gateway
    namespace: gateway-system
  rules:
  - backendRefs:
    - name: webapp-service
      port: 80
```

### API with Path-Based Routing
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api
  namespace: api
spec:
  hostnames:
  - api.civilsnut.se
  parentRefs:
  - name: shared-gateway
    namespace: gateway-system
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /v1/
    backendRefs:
    - name: api-v1-service
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /v2/
    backendRefs:
    - name: api-v2-service
      port: 8080
```

## Troubleshooting

### Gateway Not Accepting Routes
1. Check if namespace has the required label:
   ```bash
   kubectl get namespace your-namespace -o yaml | grep "gateway.networking.k8s.io/allowed"
   ```

2. Verify ReferenceGrant exists:
   ```bash
   kubectl get referencegrant -n gateway-system
   ```

### Certificate Issues
1. Check if certificate secret exists:
   ```bash
   kubectl get secret civilsnut-se-wildcard-tls -n cert-manager
   ```

2. Verify ReferenceGrant for certificate access:
   ```bash
   kubectl get referencegrant shared-gateway-cert-access -n cert-manager -o yaml
   ```

### HTTPRoute Status
Check HTTPRoute status for issues:
```bash
kubectl get httproute your-route -n your-namespace -o yaml
```

Look for status conditions that indicate problems.

### Gateway Status
Check Gateway status:
```bash
kubectl get gateway shared-gateway -n gateway-system -o yaml
```

## Benefits of Shared Gateway

1. **Reduced Resource Usage**: Single gateway instance instead of multiple
2. **Centralized TLS Management**: Direct access to cert-manager certificates
3. **Simplified Operations**: Fewer gateway objects to monitor and maintain
4. **Enhanced Security**: Namespace-based access controls
5. **Consistent Configuration**: Standardized gateway settings across services
6. **No ingress-nginx Dependency**: Pure Gateway API implementation with Cilium

## Security Considerations

- Only namespaces with proper labels can access the gateway
- TLS certificates are managed centrally with secure cross-namespace access
- RBAC ensures proper permissions for gateway management
- Regular security audits recommended for gateway configuration
- Monitor HTTPRoute creation across namespaces

## Monitoring

The shared gateway can be monitored through:
- Gateway API status conditions
- ArgoCD application health
- Cilium metrics and logs
- Kubernetes events in `gateway-system` namespace

For detailed monitoring setup, refer to the monitoring documentation in the `kube-prometheus` application.