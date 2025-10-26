# KubeVirt GitOps Setup

This directory contains the GitOps configuration for deploying KubeVirt (Kubernetes-based Virtual Machine management) using ArgoCD.

## Overview

KubeVirt allows you to run virtual machines alongside containers in Kubernetes. This setup deploys KubeVirt v1.6.2 using the official releases via GitOps methodology.

## Architecture

- **ArgoCD Application**: Deploys KubeVirt to the local cluster
- **Official Manifests**: Uses KubeVirt's official release manifests from GitHub
- **GitOps Workflow**: All changes are tracked in Git and automatically applied

## Files Structure

```
kubevirt/
├── README.md                           # This file
├── application-kubevirt.yaml           # ArgoCD Application definition
└── manifests/
    ├── kubevirt-operator.yaml         # KubeVirt operator installation job
    └── kubevirt-cr.yaml               # KubeVirt custom resource installation job
```

## Prerequisites

1. **Kubernetes Cluster** with virtualization support:
   - Hardware virtualization enabled (Intel VT-x or AMD-V)
   - Nested virtualization for cloud/VM environments
   - Kubernetes 1.28+ recommended

2. **ArgoCD** deployed and configured

3. **Node Requirements**:
   - Linux nodes with KVM support
   - `kvm` kernel module loaded
   - Sufficient resources (CPU, Memory, Storage)

## 5-Step KubeVirt Configuration and Setup

### Step 1: Verify Hardware Virtualization Support

Check if your nodes support virtualization:

```bash
# On each node, verify virtualization support
sudo apt-get update && sudo apt-get install -y cpu-checker
sudo kvm-ok

# Should return: "KVM acceleration can be used"
```

For nested virtualization (if running on VMs):
```bash
# Check if nested virtualization is enabled
cat /sys/module/kvm_intel/parameters/nested  # Intel
cat /sys/module/kvm_amd/parameters/nested    # AMD
```

### Step 2: Deploy KubeVirt via GitOps

Apply the Application to deploy KubeVirt to your local cluster:

```bash
# Apply the Application
kubectl apply -f application-kubevirt.yaml
```

This will:
- Create the `kubevirt` namespace
- Install the KubeVirt operator using the official v1.6.2 release
- Create the KubeVirt custom resource to trigger installation
- Wait for all components to be ready

### Step 3: Verify KubeVirt Installation

Check that KubeVirt is properly installed and running:

```bash
# Check KubeVirt status
kubectl get kubevirt -n kubevirt

# Verify all KubeVirt components are running
kubectl get pods -n kubevirt

# Check KubeVirt version
kubectl get kubevirt kubevirt -n kubevirt -o yaml
```

Expected output should show `Available: True` condition.

### Step 4: Install virtctl (KubeVirt CLI)

Install the KubeVirt command-line tool:

```bash
# Download and install virtctl v1.6.2
VERSION=v1.6.2
ARCH=$(uname -s | tr A-Z a-z)-$(uname -m | sed 's/x86_64/amd64/') 
curl -L -o virtctl https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-${ARCH}
chmod +x virtctl
sudo install virtctl /usr/local/bin
```

### Step 5: Create and Run Your First Virtual Machine

Create a simple VM to test the setup:

```yaml
# Save as test-vm.yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: testvm
  namespace: default
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/size: small
        kubevirt.io/domain: testvm
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
            memory: 64M
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

Apply and start the VM:

```bash
# Create the VM
kubectl apply -f test-vm.yaml

# Start the VM
virtctl start testvm

# Check VM status
kubectl get vms
kubectl get vmis

# Connect to VM console (optional)
virtctl console testvm
```

## Monitoring and Troubleshooting

### Check Installation Status

```bash
# Monitor ArgoCD Application
kubectl get applications -n argocd | grep kubevirt

# Check sync status
argocd app get kubevirt

# View KubeVirt operator logs
kubectl logs -n kubevirt deployment/virt-operator

# Check node compatibility
kubectl get nodes -o wide
kubectl describe node <node-name>
```

### Common Issues

1. **Hardware Virtualization Not Available**:
   ```bash
   # Enable nested virtualization for cloud VMs
   # AWS: Use metal instances or enable nested virtualization
   # GCP: Enable nested virtualization on the VM
   # Azure: Use Dv3/Ev3 series with nested virtualization
   ```

2. **KubeVirt Pods Not Starting**:
   ```bash
   # Check node labels and taints
   kubectl get nodes --show-labels
   
   # Ensure privileged pods can run
   kubectl describe pods -n kubevirt
   ```

3. **VM Creation Fails**:
   ```bash
   # Check VM events
   kubectl describe vm testvm
   
   # Check VMI status
   kubectl describe vmi testvm
   ```

## Virtual Machine Examples

### Ubuntu VM with DataVolume

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: ubuntu-vm
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/domain: ubuntu-vm
    spec:
      domain:
        devices:
          disks:
          - name: datavolumedisk
            disk:
              bus: virtio
          interfaces:
          - name: default
            masquerade: {}
        machine:
          type: ""
        resources:
          requests:
            memory: 1Gi
            cpu: 1
      networks:
      - name: default
        pod: {}
      volumes:
      - dataVolume:
          name: ubuntu-dv
        name: datavolumedisk
  dataVolumeTemplates:
  - metadata:
      name: ubuntu-dv
    spec:
      source:
        registry:
          url: "docker://quay.io/containerdisks/ubuntu:22.04"
      pvc:
        accessModes:
        - ReadWriteOnce
        resources:
          requests:
            storage: 5Gi
```

### Windows VM Example

```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: windows-vm
spec:
  running: false
  template:
    spec:
      domain:
        clock:
          utc: {}
          timer:
            hpet:
              present: false
            pit:
              present: false
            rtc:
              present: false
            hyperv: {}
        cpu:
          cores: 2
        devices:
          disks:
          - name: datavolumedisk
            disk:
              bus: sata
          interfaces:
          - name: default
            masquerade: {}
        features:
          acpi: {}
          apic: {}
          hyperv:
            relaxed: {}
            spinlocks:
              spinlocks: 8191
            vapic: {}
        firmware:
          bootloader:
            efi: {}
        machine:
          type: q35
        resources:
          requests:
            memory: 4Gi
      networks:
      - name: default
        pod: {}
      volumes:
      - dataVolume:
          name: windows-dv
        name: datavolumedisk
```

## Advanced Configuration

### Enable Feature Gates

Modify the KubeVirt CR to enable additional features:

```yaml
apiVersion: kubevirt.io/v1
kind: KubeVirt
metadata:
  name: kubevirt
  namespace: kubevirt
spec:
  configuration:
    developerConfiguration:
      featureGates:
        - LiveMigration
        - Snapshot
        - HotplugVolumes
        - VirtualMachineExport
```

### Resource Limits and Requests

Configure resource management:

```yaml
spec:
  configuration:
    supportContainerResources:
    - type: virt-launcher
      resources:
        requests:
          cpu: 100m
          memory: 1Gi
        limits:
          cpu: 1000m
          memory: 2Gi
```

## Useful Commands

```bash
# List all VMs
kubectl get vms --all-namespaces

# List running VMs
kubectl get vmis --all-namespaces

# Start/Stop/Restart VM
virtctl start <vm-name>
virtctl stop <vm-name>
virtctl restart <vm-name>

# Access VM console
virtctl console <vm-name>

# Access VM via VNC
virtctl vnc <vm-name>

# Migrate VM
virtctl migrate <vm-name>

# Create VM snapshot
virtctl snapshot vm <vm-name> --snapshot-name=<snapshot-name>

# Export VM
virtctl export vm <vm-name> --output=<output-file>
```

## References

- [KubeVirt Official Documentation](https://kubevirt.io/)
- [KubeVirt User Guide](https://kubevirt.io/user-guide/)
- [GitOps Demo by 0xFelix](https://github.com/0xFelix/gitops-demo) - Original inspiration
- [KubeVirt GitHub Releases](https://github.com/kubevirt/kubevirt/releases)
- [Containerized Data Importer (CDI)](https://github.com/kubevirt/containerized-data-importer)

## Support

For issues related to:
- **KubeVirt**: Check the [KubeVirt Issues](https://github.com/kubevirt/kubevirt/issues)
- **ArgoCD**: Check the [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- **This Setup**: Create an issue in this repository

---

**Note**: This setup is based on KubeVirt v1.6.2. For production environments, ensure you test thoroughly and follow security best practices.