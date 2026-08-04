# Deployment Phases Documentation

This document describes the three-phase deployment strategy for the Kubernetes infrastructure managed by FluxCD.

## Overview

The deployment is organized into three sequential phases to ensure proper dependency management and deployment order:

- **Phase 0: Foundation** - Core infrastructure components
- **Phase 1: Infrastructure** - Platform services and storage
- **Phase 2: Applications** - End-user applications and services

## Phase Structure

### Phase 0: Foundation (`00-foundation`)

Core infrastructure components that everything else depends on:

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `cert-manager` | TLS certificate management | None |
| `cilium` | CNI, Gateway API implementation, BGP | gateway-api (CRDs) |
| `coredns` | Corefile customizations (ts.net rewrite for OIDC) | None |
| `external-secrets` | Secrets management from external sources | None |
| `gateway-api` | Gateway API CRDs (experimental channel) | None |
| `onepassword-connect` | 1Password sync for external-secrets | external-secrets |
| `prometheus-operator-crds` | Prometheus Operator CRDs (ahead of kube-prometheus-stack) | None |

**Deployment Order**: These components can mostly deploy in parallel; CRD providers precede their consumers.

### Phase 1: Infrastructure (`01-infrastructure`)

Platform services that provide foundational capabilities:

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `shared-gateway` | Gateway API gateway for ingress | cilium, cert-manager |
| `rook-ceph` | Distributed block storage + RGW object store | None |
| `cnpg` | CloudNativePG Postgres operator | rook-ceph (PVCs), external-secrets |
| `zitadel` | Self-hosted OIDC identity provider | cnpg, shared-gateway, external-secrets |
| `oauth2-proxy` | ext_authz bridge for Gateway API ExternalAuth | zitadel, shared-gateway |
| `tinkerbell` | Bare-metal PXE provisioning (Flatcar) | rook-ceph |

**Deployment Order**: Depends on Phase 0 completion.

### Phase 2: Applications (`02-applications`)

End-user applications and monitoring services:

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `flux-web` | Flux Operator web UI | shared-gateway, zitadel (OIDC) |
| `home-assistant` | Home automation platform | external-secrets, rook-ceph, shared-gateway |
| `httpbin` | Test / debug endpoint | shared-gateway |
| `monitoring` | kube-prometheus-stack + Loki + Alloy + InfluxDB + Signal alerting | rook-ceph, shared-gateway |
| `mqtt` | MQTT message broker | external-secrets |
| `zigbee2mqtt` | Zigbee to MQTT bridge | external-secrets, rook-ceph, shared-gateway |

**Deployment Order**: Depends on Phase 0 and Phase 1 completion.

## Additional Dependencies

### External Secrets Ecosystem

- `onepassword-connect`: Depends on `external-secrets` for CRDs and operator

### Application-Specific Dependencies

- **MQTT applications** (`mqtt`, `zigbee2mqtt`): Require `external-secrets` for credential management
- **Storage-dependent applications** (`home-assistant`, `monitoring`, `zigbee2mqtt`): Require `rook-ceph` (`ceph-block` StorageClass) for persistent storage
- **Web applications** (`home-assistant`, `zigbee2mqtt`, `monitoring`, `flux-web`): Require `shared-gateway` for external access

## FluxCD Integration

### Automatic Discovery

The FluxInstance automatically discovers directories under `fluxcd/` and creates Kustomizations. The numbered prefixes (`00-`, `01-`, `02-`) ensure alphabetical ordering.

### Dependency Management

Dependencies are managed through:

1. **Directory ordering**: Phases are processed in alphabetical order
2. **Annotations**: `flux.weave.works/depends-on` annotations in kustomization.yaml files
3. **Health checks**: FluxCD waits for component health before proceeding

### Example Deployment Flow

```
Phase 0 (Foundation):
cert-manager ─────┐
cilium ───────────┤
coredns ──────────┤
external-secrets ─┼── Wait for all Phase 0 to be Ready
gateway-api ──────┤
1password-connect ┤
prom-op-crds ─────┘

Phase 1 (Infrastructure):
shared-gateway ──┐
rook-ceph ───────┤
cnpg ────────────┼── Wait for all Phase 1 to be Ready
zitadel ─────────┤
oauth2-proxy ────┤
tinkerbell ──────┘

Phase 2 (Applications):
flux-web ────────┐
home-assistant ──┤
httpbin ─────────┤
monitoring ──────┼── Deploy in parallel
mqtt ────────────┤
zigbee2mqtt ─────┘
```

## Troubleshooting

### Common Issues

1. **Stuck deployments**: Check dependencies are healthy
   ```bash
   kubectl get kustomizations -n flux-system
   ```

2. **Missing CRDs**: Ensure foundation phase completed successfully
   ```bash
   kubectl get crd | grep -E "(gateway|cilium|external-secrets)"
   ```

3. **Storage issues**: Verify Rook-Ceph is operational
   ```bash
   kubectl get pods -n rook-ceph
   kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
   ```

### Dependency Verification

Check component status:
```bash
# Foundation phase
kubectl get pods -n cert-manager
kubectl get pods -n kube-system -l k8s-app=cilium
kubectl get pods -n external-secrets

# Infrastructure phase  
kubectl get gateway -n gateway-system
kubectl get storageclass ceph-block

# Applications phase
kubectl get pods -n monitoring  # kube-prometheus-stack, Loki, Alloy, Signal alerting
kubectl get pods -n mosquitto   # mqtt
kubectl get pods -n home-assistant
kubectl get pods -n zigbee2mqtt
```

## Migration Strategy

### From Single-Phase to Multi-Phase

If migrating from a single deployment approach:

1. **Backup current state**
2. **Move components to appropriate phases**
3. **Add dependency annotations**
4. **Test phase-by-phase deployment**
5. **Monitor for any circular dependencies**

### Adding New Components

When adding new components:

1. **Identify dependencies** - What does this component need?
2. **Determine phase** - Which phase should host this component?
3. **Update documentation** - Add to this document
4. **Test deployment** - Verify dependency chain works

## Best Practices

### Component Placement

- **Foundation**: Components with no dependencies on other services
- **Infrastructure**: Platform services that applications depend on
- **Applications**: End-user facing services and applications

### Dependency Management

- **Minimize cross-phase dependencies**: Try to keep dependencies within the same phase or to earlier phases
- **Explicit annotations**: Always document dependencies in kustomization.yaml
- **Health checks**: Configure appropriate health checks for each component

### Naming Conventions

- **Phase directories**: Use numeric prefixes (`00-`, `01-`, `02-`)
- **Component names**: Use descriptive names that match their function
- **Labels**: Consistent labeling across all components in a phase

This phased approach ensures reliable, predictable deployments with proper dependency management and rollback capabilities.