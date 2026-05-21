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
| `cilium` | CNI and Gateway API CRDs | None |
| `external-secrets` | Secrets management from external sources | None |

**Deployment Order**: These components can deploy in parallel as they have no interdependencies.

### Phase 1: Infrastructure (`01-infrastructure`)

Platform services that provide foundational capabilities:

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `shared-gateway` | Gateway API gateway for ingress | cilium (for Gateway CRDs) |
| `longhorn` | Distributed block storage | cert-manager (for TLS) |

**Deployment Order**: Depends on Phase 0 completion.

### Phase 2: Applications (`02-applications`)

End-user applications and monitoring services:

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| `home-assistant` | Home automation platform | external-secrets, longhorn, shared-gateway |
| `ingress-nginx` | NGINX ingress controller | cert-manager, shared-gateway |
| `mqtt` | MQTT message broker | external-secrets |
| `vm-stack` | Victoria Metrics monitoring | longhorn, shared-gateway |
| `zigbee2mqtt` | Zigbee to MQTT bridge | external-secrets, longhorn, shared-gateway |

**Deployment Order**: Depends on Phase 0 and Phase 1 completion.

## Additional Dependencies

### External Secrets Ecosystem

- `onepassword-connect`: Depends on `external-secrets` for CRDs and operator

### Application-Specific Dependencies

- **MQTT applications** (`mqtt`, `zigbee2mqtt`): Require `external-secrets` for credential management
- **Storage-dependent applications** (`home-assistant`, `vm-stack`, `zigbee2mqtt`): Require `longhorn` for persistent storage
- **Web applications** (`home-assistant`, `zigbee2mqtt`, `vm-stack`): Require `shared-gateway` for external access

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
cert-manager ──┐
cilium ────────┼── Wait for all Phase 0 to be Ready
external-secrets ┘

Phase 1 (Infrastructure):
shared-gateway ──┐── Wait for all Phase 1 to be Ready  
longhorn ────────┘

Phase 2 (Applications):
home-assistant ──┐
ingress-nginx ───┤
mqtt ────────────┼── Deploy in parallel
vm-stack ────────┤
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

3. **Storage issues**: Verify Longhorn is operational
   ```bash
   kubectl get pods -n longhorn-system
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
kubectl get storageclass longhorn

# Applications phase
kubectl get pods -n monitoring  # vm-stack
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