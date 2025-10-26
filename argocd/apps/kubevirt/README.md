# KubeVirt GitOps Setup (Helm-based)

This directory contains the GitOps configuration for deploying KubeVirt (Kubernetes-based Virtual Machine management) using ArgoCD and the [kubevirt-community-stack](https://cloudymax.github.io/kubevirt-community-stack/) Helm chart.

## Overview

KubeVirt allows you to run virtual machines alongside containers in Kubernetes. This setup uses a modern Helm-based approach with the kubevirt-community-stack (v0.1.0), providing:

- **KubeVirt Operator**: Core virtualization platform
- **Containerized Data Importer (CDI)**: Import VM images from various sources
- **Web UI**: Kubevirt-manager for VM management (enabled with HTTP route)
- **Optional Cluster API**: Create Kubernetes clusters using VMs

## Architecture

- **ArgoCD Application**: Manages KubeVirt deployment using Helm
- **Helm Chart**: kubevirt-community-stack from CloudyMax
- **GitOps Workflow**: All changes tracked in Git and automatically applied
- **Modular Components**: Enable/disable features as needed

## Files Structure

```
kubevirt/
├── README.md                           # This file
├── application-kubevirt.yaml           # ArgoCD Application definition (kubevirt-stack v0.1.0)
├── httproute.yaml                      # HTTP route for kubevirt-manager web UI
└── referencegrant.yaml                 # ReferenceGrant for gateway access
```

## Component Versions

This deployment uses the following chart versions:

- **kubevirt-stack**: v0.1.0 (meta-chart)
- **kubevirt**: v0.3.0 (KubeVirt v1.5.2)
- **kubevirt-cdi**: v0.2.2 (CDI v1.63.0)
- **kubevirt-manager**: v0.3.0 (Manager v1.5.3)

## Prerequisites

### 1. Hardware Requirements

**Bare Metal or VM with Nested Virtualization**:
```bash
# Check virtualization support
sudo apt-get install -y libvirt-clients
virt-host-validate qemu

# Expected output:
# QEMU: Checking for hardware virtualization          : PASS
# QEMU: Checking if device /dev/kvm exists            : PASS
# QEMU: Checking if device /dev/kvm is accessible     : PASS
# QEMU: Checking if device /dev/vhost-net exists      : PASS
# QEMU: Checking if device /dev/net/tun exists        : PASS
```

### 2. Kubernetes Cluster Requirements

- **Kubernetes 1.28+** recommended
- **Node Resources**: Sufficient CPU, Memory, and Storage
- **Architecture**: AMD64 nodes (ARM64 support limited)
- **CPUManager Policy**: Recommended to set `cpuManagerPolicy: static` in kubelet config for performance

### 3. ArgoCD

- ArgoCD deployed and configured in your cluster
- Access to apply applications in the `argocd` namespace

### 4. Storage

- **Default StorageClass** or configure specific StorageClass for VM disks
- **Fast Storage** recommended for better VM performance (NVMe, SSD)

## Quick Start

### Deploy KubeVirt Stack

The deployment includes the kubevirt-manager web UI accessible at `kubevirt-manager.civilsnut.se`.

```bash
# Apply the ArgoCD Application
kubectl apply -f application-kubevirt.yaml

# Monitor the deployment
kubectl get applications -n argocd kubevirt
argocd app get kubevirt
```

### Verify Installation

```bash
# Check KubeVirt status
kubectl get kubevirt -n kubevirt

# Verify all components are running
kubectl get pods -n kubevirt
kubectl get pods -n cdi

# Check KubeVirt version and status
kubectl get kubevirt kubevirt -n kubevirt -o yaml
```

## Configuration

The ArgoCD application includes sensible defaults, but you can customize the deployment by modifying the Helm values in `application-kubevirt.yaml`.

### Key Configuration Options

#### KubeVirt Core Settings

```yaml
kubevirt:
  enabled: true
  spec:
    configuration:
      developerConfiguration:
        featureGates:
          - LiveMigration      # Enable VM live migration
          - Snapshot          # Enable VM snapshots
          - HotplugVolumes    # Enable volume hotplug
          - VirtualMachineExport  # Enable VM export
        useEmulation: false   # Set to true if no hardware virtualization
      virtualMachineInstancesPerNode: 10  # Max VMs per node
```

#### CDI (Containerized Data Importer) Settings

```yaml
kubevirt-cdi:
  enabled: true
  spec:
    config:
      featureGates:
        - HonorWaitForFirstConsumer  # Better storage handling
```

#### Optional Components

```yaml
# Web UI for VM management
kubevirt-manager:
  enabled: false  # Set to true to enable web interface

# Cluster API for creating k8s clusters with VMs
cluster-api-operator:
  enabled: false  # Set to true for multi-cluster scenarios
```

## Creating Virtual Machines

### Install virtctl CLI

```bash
# Latest version
export VERSION=$(curl -s https://api.github.com/repos/kubevirt/kubevirt/releases/latest | jq -r .tag_name)
curl -L -o virtctl https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-linux-amd64
chmod +x virtctl
sudo mv virtctl /usr/local/bin/

# Or via kubectl plugin
kubectl krew install virt
```

### Basic VM Example

Create a simple test VM:

```yaml
# test-vm.yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: test-vm
  namespace: kubevirt
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/domain: test-vm
    spec:
      domain:
        devices:
          disks:
            - name: containerdisk
              disk:
                bus: virtio
            - name: cloudinitdisk
              disk:
                bus: virtio
          interfaces:
            - name: default
              masquerade: {}
        resources:
          requests:
            memory: 1Gi
            cpu: 1
      networks:
        - name: default
          pod: {}
      volumes:
        - name: containerdisk
          containerDisk:
            image: quay.io/kubevirt/cirros-container-disk-demo
        - name: cloudinitdisk
          cloudInitNoCloud:
            userDataBase64: SGkuXG4=
```

```bash
# Create and start the VM
kubectl apply -f test-vm.yaml
virtctl start test-vm -n kubevirt

# Check VM status
kubectl get vms -n kubevirt
kubectl get vmis -n kubevirt

# Connect to VM console
virtctl console test-vm -n kubevirt
```

### Advanced VM with Custom Image

```yaml
# ubuntu-vm.yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: ubuntu-vm
  namespace: kubevirt
spec:
  running: false
  template:
    spec:
      domain:
        devices:
          disks:
            - name: ubuntu-disk
              disk:
                bus: virtio
          interfaces:
            - name: default
              masquerade: {}
        resources:
          requests:
            memory: 2Gi
            cpu: 2
      networks:
        - name: default
          pod: {}
      volumes:
        - name: ubuntu-disk
          dataVolume:
            name: ubuntu-dv
  dataVolumeTemplates:
    - metadata:
        name: ubuntu-dv
      spec:
        source:
          http:
            url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
        storage:
          resources:
            requests:
              storage: 10Gi
          storageClassName: fast-ssd  # Adjust to your storage class
        accessModes:
          - ReadWriteOnce
```

### Using the Helm Chart for VMs

You can also use the kubevirt-vm Helm chart for more complex VM definitions:

```bash
# Add the repo if not already done
helm repo add kubevirt https://cloudymax.github.io/kubevirt-community-stack

# Create a VM using Helm
helm install my-vm kubevirt/kubevirt-vm \
  --namespace kubevirt \
  --set virtualMachine.name="my-vm" \
  --set virtualMachine.machine.vCores=2 \
  --set virtualMachine.machine.memory.base="4Gi" \
  --set disks[0].name="root-disk" \
  --set disks[0].pvsize="20Gi" \
  --set disks[0].source="url" \
  --set disks[0].url="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
```

## Management and Operations

### Common VM Operations

```bash
# List VMs
kubectl get vms -A

# Start/Stop/Restart VM
virtctl start my-vm -n kubevirt
virtctl stop my-vm -n kubevirt  
virtctl restart my-vm -n kubevirt

# Access VM console
virtctl console my-vm -n kubevirt

# Access VM via VNC (requires VNC client)
virtctl vnc my-vm -n kubevirt

# Port forwarding to VM
virtctl port-forward --address=0.0.0.0 my-vm 8080:80 -n kubevirt
```

### Live Migration

```bash
# Migrate VM to another node
virtctl migrate my-vm -n kubevirt

# Check migration status
kubectl get vmim -n kubevirt
```

### Snapshots (if enabled)

```bash
# Create snapshot
virtctl snapshot vm my-vm --snapshot-name=backup-$(date +%Y%m%d) -n kubevirt

# List snapshots
kubectl get vmsnapshot -n kubevirt

# Restore from snapshot
kubectl apply -f - <<EOF
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: restored-vm
spec:
  dataVolumeTemplates:
  - metadata:
      name: restored-dv
    spec:
      source:
        snapshot:
          namespace: kubevirt
          name: my-vm-backup-20231201
      storage:
        resources:
          requests:
            storage: 20Gi
EOF
```

### Data Volume Management

```bash
# List data volumes
kubectl get dv -n kubevirt

# Import from URL
kubectl apply -f - <<EOF
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: imported-image
  namespace: kubevirt
spec:
  source:
    http:
      url: "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
  storage:
    resources:
      requests:
        storage: 10Gi
    accessModes:
    - ReadWriteOnce
EOF
```

## Monitoring and Troubleshooting

### Check Installation Status

```bash
# ArgoCD Application status
kubectl get application kubevirt -n argocd -o yaml

# KubeVirt operator logs
kubectl logs -n kubevirt deployment/virt-operator

# CDI operator logs
kubectl logs -n cdi deployment/cdi-operator
```

### Common Issues

1. **Hardware Virtualization Not Available**:
   ```bash
   # Enable emulation mode
   kubectl patch kubevirt kubevirt -n kubevirt --type merge -p '{"spec":{"configuration":{"developerConfiguration":{"useEmulation":true}}}}'
   ```

2. **VM Not Starting**:
   ```bash
   # Check VM events
   kubectl describe vm my-vm -n kubevirt
   
   # Check VMI events if VM started
   kubectl describe vmi my-vm -n kubevirt
   ```

3. **Storage Issues**:
   ```bash
   # Check DataVolume status
   kubectl get dv -n kubevirt
   kubectl describe dv my-dv -n kubevirt
   
   # Check PVC status
   kubectl get pvc -n kubevirt
   ```

## Web UI Access

The kubevirt-manager web interface is enabled and accessible via HTTP route:

- **URL**: https://kubevirt-manager.civilsnut.se
- **Namespace**: kubevirt-manager
- **Service**: kubevirt-manager:8080

### Alternative Local Access

If you need local access for development:

```bash
# Port-forward to access locally
kubectl port-forward -n kubevirt-manager service/kubevirt-manager 8080:8080

# Access at http://localhost:8080
```

### Web UI Features

The kubevirt-manager provides:
- Visual VM creation and management
- VM console access through the browser
- Resource monitoring and metrics
- VM lifecycle operations (start, stop, restart, delete)
- Network and storage configuration

## Performance Tuning

### For Production Workloads

```yaml
kubevirt:
  spec:
    configuration:
      # Use host CPU model for better performance
      cpuModel: "host-model"
      
      # Dedicated CPU policy
      # Requires cpuManagerPolicy: static in kubelet
      # and appropriate node labeling
      
      # Memory settings
      memoryOvercommit: 150  # 150% overcommit
      
      # Network performance
      network:
        defaultNetworkInterface: "bridge"  # Better performance than masquerade
        
    # Node placement for compute-intensive workloads
    workloads:
      nodePlacement:
        nodeSelector:
          node-role.kubernetes.io/worker: ""
          kubevirt.io/schedulable: "true"
```

## Upgrading

KubeVirt upgrades are handled through ArgoCD by updating the Helm chart version:

```bash
# Check current version
argocd app get kubevirt

# Trigger sync to get latest chart version
argocd app sync kubevirt

# Monitor upgrade progress
kubectl get kubevirt kubevirt -n kubevirt -w
```

## Uninstalling

To completely remove KubeVirt:

```bash
# Delete the ArgoCD application
kubectl delete application kubevirt -n argocd

# If resources are stuck, force cleanup
kubectl delete kubevirt kubevirt -n kubevirt --wait=true
kubectl delete apiservices v1.subresources.kubevirt.io
kubectl delete mutatingwebhookconfigurations virt-api-mutator
kubectl delete validatingwebhookconfigurations virt-operator-validator virt-api-validator

# Clean up namespaces if stuck
kubectl get namespace kubevirt -o json | \
  tr -d "\n" | sed "s/\"finalizers\": \[[^]]\+\]/\"finalizers\": []/" | \
  kubectl replace --raw /api/v1/namespaces/kubevirt/finalize -f -
```

## Security Considerations

1. **Pod Security Standards**: KubeVirt requires privileged containers
2. **Network Policies**: Implement appropriate network isolation
3. **RBAC**: Review and customize RBAC permissions as needed
4. **VM Images**: Only use trusted VM images from verified sources
5. **Storage**: Ensure proper storage encryption for sensitive workloads

## Useful Commands Reference

```bash
# VM Management
virtctl start/stop/restart <vm-name> -n <namespace>
virtctl console <vm-name> -n <namespace>
virtctl vnc <vm-name> -n <namespace>
virtctl ssh <user>@<vm-name>.<namespace>

# Information
kubectl get vms,vmis,dvs -A
kubectl describe vm <vm-name> -n <namespace>
virtctl version

# Troubleshooting  
kubectl logs -n kubevirt deployment/virt-operator
kubectl get events -n kubevirt --sort-by='.lastTimestamp'

# Performance
kubectl top nodes
kubectl top pods -n kubevirt
```

## References

- [KubeVirt Official Documentation](https://kubevirt.io/)
- [KubeVirt Community Stack](https://cloudymax.github.io/kubevirt-community-stack/)
- [KubeVirt User Guide](https://kubevirt.io/user-guide/)
- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [Containerized Data Importer](https://github.com/kubevirt/containerized-data-importer)

## Support

For issues related to:
- **KubeVirt**: Check the [KubeVirt Issues](https://github.com/kubevirt/kubevirt/issues)
- **Helm Chart**: Check the [Community Stack Issues](https://github.com/cloudymax/kubevirt-community-stack/issues)
- **ArgoCD**: Check the [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- **This Setup**: Create an issue in this repository

---

**Note**: This setup uses the kubevirt-community-stack Helm chart (v0.1.0) which provides a more maintainable and configurable approach compared to direct manifest deployment. The chart is actively maintained and includes additional useful components for a complete virtualization stack.