# Tinkerbell PXE Provisioning Plan — Flatcar on Bare Metal (10-Step)

**Status:** Draft — Requires Step 0 validation before execution  
**Target:** PXE-boot bare-metal nodes, stream Flatcar image, form Kubernetes cluster  
**Provisioning Cluster:** Existing K8s with Cilium (BGP + Gateway API)  
**Target OS:** Flatcar Linux (Ignition-based, immutable)  
**BMC/IPMI:** None — manual power-on only  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Bootstrap Kubernetes Cluster                        │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Cilium CNI (BGP + Gateway API)                                  ││
│  │    └─ CiliumLoadBalancerIPPool: 10.80.0.0/29                     ││
│  │    └─ CiliumBGPAdvertisement → upstream router (relay peer)       ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Tinkerbell (Helm chart, rufio disabled)                           ││
│  │    ├─ smee   → DHCP + iPXE + TFTP + HTTP (LoadBalancer: 10.80.0.1)││
│  │    ├─ tink   → workflow engine                                    ││
│  │    └─ hegel  → metadata / Ignition config                         ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ L3 BGP-advertised route
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Bare-Metal VLAN (192.168.20.0/24)                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────────┐│
│  │  Gateway Router          │    │  Bare-Metal Nodes               ││
│  │  - Default gateway:      │    │  - MAC: aa:bb:cc:dd:ee:{01..N} ││
│  │    192.168.20.1          │    │  - Manual power-on              ││
│  │  - DHCP relay:           │    │  - PXE → iPXE → HookOS →        ││
│  │    ip helper-address     │    │    oci2disk → Ignition →       ││
│  │    10.80.0.1             │    │    Flatcar → K8s join          ││
│  │  - BGP peer w/ Cilium    │    │                                 ││
│  └─────────────────────────┘    └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

**Key Design Decision:** smee runs **without `hostNetwork`**. Because Tinkerbell lives on a different L2 segment from the bare-metal nodes, DHCP broadcasts never reach smee directly. A **DHCP relay agent** on the bare-metal VLAN's gateway catches the broadcast DISCOVER and forwards it as L3 unicast to smee's LoadBalancer IP (10.80.0.1), which is advertised via BGP to the relay router.

---

## Prerequisites

| Requirement | Status | Notes |
|---|---|---|
| Existing K8s cluster with Cilium | ✅ | BGP and Gateway API enabled |
| BGP peering with upstream router | ⚠️ | Must peer with relay router |
| Bare-metal VLAN with gateway | ✅ | 192.168.20.0/24 assumed |
| DHCP relay capability on gateway | ⚠️ | `ip helper-address` / `dhcrelay` |
| Flatcar image URL | ❌ | Need to identify/source |
| Flatcar Ignition configs | ❌ | For K8s bootstrap |
| Unused /29 for LB pool | ⚠️ | 10.80.0.0/29 proposed |

---

## Critical Unknown (Resolve Before Step 1)

**Does a DHCP server already exist on the bare-metal VLAN (192.168.20.0/24)?**

This determines smee's DHCP mode and the relay configuration:

| Existing DHCP? | smee `dhcp.mode` | Relay `helper-address` Targets |
|---|---|---|
| **Yes** — server answers | `proxy` | BOTH existing DHCP server IP **AND** 10.80.0.1 |
| **No** — nothing answers | `full` | 10.80.0.1 **only** |

**Detection method:**

```bash
# On a host in the bare-metal VLAN (192.168.20.0/24)
sudo tcpdump -i <iface> -n 'port 67 or port 68' 
  -e -tttt -v

# In another terminal, power on / reboot a bare-metal node
# Watch for DHCP DISCOVER (broadcast) and OFFER (unicast from server)

# If you see an OFFER from an IP other than 10.80.0.1 → existing server
# If you see ONLY DISCOVER with no OFFER → no existing server
```

> ⚠️ **WARNING:** Running smee in `full` mode alongside an existing DHCP server causes IP lease conflicts and intermittent PXE failures. **Confirm this first.**

---

## Step 1: Reserve and Advertise LoadBalancer IP Pool

Create a Cilium LoadBalancer IP pool for Tinkerbell services. This pool provides the routable IP (10.80.0.1) that smee will use.

### 1A. Create IP Pool

```yaml
# fluxcd/01-infrastructure/tinkerbell/cilium-lb-pool.yaml
apiVersion: cilium.io/v2alpha1
kind: CiliumLoadBalancerIPPool
metadata:
  name: tinkerbell-pool
  namespace: tinkerbell
spec:
  blocks:
    - cidr: 10.80.0.0/29  # 10.80.0.1 - 10.80.0.6
  serviceSelector:
    matchLabels:
      io.tinkerbell/pool: "true"
```

### 1B. Advertise Pool via BGP

```yaml
# fluxcd/01-infrastructure/tinkerbell/cilium-bgp-advertisement.yaml
apiVersion: cilium.io/v2alpha1
kind: CiliumBGPAdvertisement
metadata:
  name: tinkerbell-services
  namespace: tinkerbell
spec:
  advertisements:
    - advertisementType: Service
      service:
        addresses:
          - LoadBalancerIP
      selector:
        matchLabels:
          io.tinkerbell/pool: "true"
```

### 1C. Verify BGP Peer Configuration

Ensure Cilium has a BGP peer configuration for the upstream router that will run the DHCP relay. The router MUST learn the 10.80.0.0/29 route.

```bash
# Check existing peer configs
kubectl get CiliumBGPPeerConfig -A

# Example peer config (if not existing)
apiVersion: cilium.io/v2alpha1
kind: CiliumBGPPeerConfig
metadata:
  name: upstream-router
  namespace: tinkerbell
spec:
  peerConfigRefs:
    - name: tinkerbell-peer
  virtualRouters:
    - localASN: 64501
      exportPodCIDR: false
      neighbors:
        - peerAddress: "192.168.1.1/32"  # Relay router IP
          peerASN: 64500
          ebgpMultihop: false
```

### 1D. Validation

```bash
# Check Cilium BGP routes
kubectl -n kube-system exec -it cilium-xxxx -- cilium bgp routes

# On the relay router, verify route to 10.80.0.0/29
show ip route 10.80.0.0
# OR
ip route get 10.80.0.1
```

**✅ Success Criteria:**
- [ ] Cilium BGP advertisement shows 10.80.0.0/29
- [ ] Relay router has a route to 10.80.0.1 via its BGP peer

---

## Step 2: Configure DHCP Relay on Bare-Metal Gateway

Configure the gateway router for the bare-metal VLAN (192.168.20.0/24) to relay DHCP requests to smee's IP.

### Based on Step 0 findings:

**If NO existing DHCP server (smee mode: `full`):**
```
# Cisco IOS
interface Vlan20
  ip helper-address 10.80.0.1

# Juniper JunOS
set forwarding-options helpers dhcp-relay server-group smee 10.80.0.1
set forwarding-options helpers dhcp-relay group baremetal-vlan interface vlan.20

# Linux (dhcp-relay / isc-dhcp-relay)
dhcrelay -i eth0 -a 10.80.0.1

# VyOS
set service dhcp-relay interface eth0
set service dhcp-relay relay-options server 10.80.0.1
```

**If YES existing DHCP server at 192.168.20.10 (smee mode: `proxy`):**
```
# Cisco IOS
interface Vlan20
  ip helper-address 192.168.20.10   # Existing DHCP server
  ip helper-address 10.80.0.1       # smee for PXE options

# Linux
dhcrelay -i eth0 -a 192.168.20.10 -a 10.80.0.1
```

### Validation

```bash
# On relay router, capture DHCP relay traffic
tcpdump -i <baremetal-iface> -n 'udp port 67 or port 68' 

# Power on a node — you should see:
# 1. DISCOVER broadcast from node
# 2. Relay forwarding DISCOVER as unicast to 10.80.0.1 (and existing DHCP if proxy mode)
# 3. OFFER/ACK from server(s) back through relay
```

**✅ Success Criteria:**
- [ ] Relay forwards DISCOVER to 10.80.0.1
- [ ] OFFER returns through relay to client

---

## Step 3: Install Tinkerbell with LoadBalancer Services

Install Tinkerbell Helm chart with smee configured for LoadBalancer (not `hostNetwork`).

### 3A. Create Namespace

```yaml
# fluxcd/01-infrastructure/tinkerbell/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tinkerbell
  labels:
    name: tinkerbell
```

### 3B. Helm Values

```yaml
# fluxcd/01-infrastructure/tinkerbell/values.yaml
rufio:
  enabled: false  # No BMC/IPMI support needed

smee:
  hostNetwork: false  # Critical: use LoadBalancer, not host network
  publicIP: "10.80.0.1"  # Must match advertised LB IP
  trustedProxies: "10.244.0.0/16"  # Replace with your Cilium pod CIDR
  
  # DHCP mode — SET BASED ON STEP 0
  # Mode must match the relay configuration from Step 2
  dhcp:
    mode: "full"  # Change to "proxy" if existing DHCP server exists
    
    # For proxy mode: existing DHCP server IP
    # proxyServer: "192.168.20.10"
    
    # IP range for full mode (only if mode: full)
    # range:
    #   start: "192.168.20.100"
    #   end: "192.168.20.200"
    #   netmask: "255.255.255.0"
    #   gateway: "192.168.20.1"

  service:
    type: LoadBalancer
    labels:
      io.tinkerbell/pool: "true"
    annotations:
      io.cilium/lb-ipam-ips: "10.80.0.1"  # Pin to specific IP from pool
    ports:
      - name: dhcp
        port: 67
        protocol: UDP
        targetPort: 67
      - name: tftp
        port: 69
        protocol: UDP
        targetPort: 69
      - name: http
        port: 80
        protocol: TCP
        targetPort: 8080
      - name: syslog
        port: 514
        protocol: UDP
        targetPort: 514

tink:
  service:
    type: ClusterIP  # Internal only

hegel:
  service:
    type: ClusterIP  # Internal only

# Enable Gateway API integration if needed
# gateway:
#   enabled: true
```

### 3C. Helm Release

```yaml
# fluxcd/01-infrastructure/tinkerbell/helm-release.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: tinkerbell
  namespace: tinkerbell
spec:
  interval: 5m
  chart:
    spec:
      chart: tinkerbell
      version: 0.20.0  # Use latest stable version
      sourceRef:
        kind: HelmRepository
        name: tinkerbell
        namespace: flux-system
  valuesFrom:
    - kind: ConfigMap
      name: tinkerbell-values
  values:
    rufio:
      enabled: false
```

### 3D. Verify Installation

```bash
# Check all pods are running
kubectl get pods -n tinkerbell

# Check services have LoadBalancer IP
kubectl get svc -n tinkerbell

# Verify smee service has 10.80.0.1
kubectl get svc -n tinkerbell smee -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

**✅ Success Criteria:**
- [ ] All Tinkerbell pods: Running
- [ ] smee service: LoadBalancer with IP 10.80.0.1
- [ ] All required ports exposed (67/udp, 69/udp, 80/tcp, 514/udp)

---

## Step 4: Verify DHCP and PXE Chain

Test that a node can get a DHCP lease and receive the iPXE bootstrap.

### 4A. Manual DHCP Test

```bash
# From a test VM or bare-metal node on 192.168.20.0/24
# Force DHCP renewal and watch

# On Linux test host:
sudo dhclient -v -r eth0 && sudo dhclient -v eth0

# Or use a PXE tester tool
```

### 4B. Capture PXE Bootstrap

```bash
# On a node, boot with PXE and capture network traffic
tcpdump -i eth0 -n -w pxe_test.pcap 'port 67 or port 68 or port 69 or port 80'

# You should see:
# 1. DHCP DISCOVER → OFFER/ACK with PXE options (next-server, bootstrap file)
# 2. TFTP request for iPXE binary
# 3. HTTP request for iPXE script
```

### 4C. Check smee Logs

```bash
kubectl logs -n tinkerbell -l app.kubernetes.io/instance=tinkerbell,app.kubernetes.io/name=smee

# Look for:
# - DHCP DISCOVER received
# - OFFER sent
# - TFTP request served
# - iPXE script delivered
```

**✅ Success Criteria:**
- [ ] DHCP OFFER received with PXE options (next-server=10.80.0.1)
- [ ] iPXE binary loaded via TFTP
- [ ] iPXE script fetched via HTTP from 10.80.0.1

---

## Step 5: Prepare Flatcar Image and Artifacts

Prepare the Flatcar image and Ignition configurations for provisioning.

### 5A. Source Flatcar Image

```bash
# Download Flatcar image (example: stable channel)
FLATCAR_VERSION="3760.2.0"  # Update to latest stable
wget https://stable.release.flatcar-linux.net/amd64-usr/${FLATCAR_VERSION}/flatcar_production_image.bin.gz

# Host the image via HTTP (use any web server in the tinkerbell namespace)
# Option: Use hegel's artifact serving
```

### 5B. Create ConfigMap for Flatcar Image

```yaml
# fluxcd/01-infrastructure/tinkerbell/flatcar-image-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: flatcar-image
  namespace: tinkerbell
binaryData:
  flatcar_production_image.bin.gz: |-
    <base64-encoded-image-contents>
```

> **Note:** For large images, consider using an external HTTP server or a PersistentVolume. Tinkerbell's hegel can serve artifacts from its HTTP endpoint.

### 5C. Prepare Ignition Config

Create Ignition configurations for Flatcar. Use `ignition.config.url` to have Flatcar fetch its config from hegel on each boot.

```yaml
# Example minimal Ignition for K8s node
# This would be served by hegel at http://10.80.0.1:50060/metadata/<hardware-id>
{
  "ignition": {
    "version": "3.4.0",
    "configMerge": [
      {
        "source": "http://10.80.0.1:50060/metadata/{{ .HardwareID }}"
      }
    ]
  },
  "storage": {
    "files": [
      {
        "path": "/etc/kubernetes/manifests/kubelet.yaml",
        "contents": {
          "source": "data:text/plain;base64,<base64-kubelet-config>"
        }
      }
    ]
  },
  "systemd": {
    "units": [
      {
        "name": "kubelet.service",
        "enabled": true
      }
    ]
  }
}
```

**Recommended:** Use **Typhoon** patterns (https://github.com/poseidon/typhoon) for Flatcar + K8s Ignition configs.

---

## Step 6: Create Tinkerbell Hardware, Template, and Workflow CRDs

Define the provisioning workflow for each bare-metal node.

### 6A. Hardware CRD

```yaml
# fluxcd/01-infrastructure/tinkerbell/hardware-node01.yaml
apiVersion: tinkerbell.org/v1alpha1
kind: Hardware
metadata:
  name: node01
  namespace: tinkerbell
spec:
  disks:
    - device: /dev/sda
      # For NVMe: /dev/nvme0n1
  interfaces:
    - dhcp:
        mac: aa:bb:cc:dd:ee:01
        ip:
          address: 192.168.20.21
          netmask: 255.255.255.0
          gateway: 192.168.20.1
        hostname: node01
      netboot:
        allowPXE: true
        allowWorkflow: true
  metadata:
    instance:
      id: aa:bb:cc:dd:ee:01
    facility:
      facility_code: lab
```

### 6B. Template CRD

```yaml
# fluxcd/01-infrastructure/tinkerbell/template-flatcar.yaml
apiVersion: tinkerbell.org/v1alpha1
kind: Template
metadata:
  name: flatcar-k8s
  namespace: tinkerbell
spec:
  data: |
    version: "0.1"
    name: flatcar-k8s-workflow
    tasks:
      - name: provision
        worker: "{{.device_1}}"
        volumes:
          - /dev:/dev
          - /dev/console:/dev/console
          - /ignition:/ignition
        actions:
          # Step 1: Stream Flatcar image to disk
          - name: stream-flatcar
            image: quay.io/tinkerbell/actions/oci2disk:v1.0.0
            timeout: 300
            environment:
              IMG_URL: "http://10.80.0.1:8080/flatcar_production_image.bin.gz"
              DEST_DISK: /dev/sda
              COMPRESSED: "true"
              IMG_SIZE: "2000000000"  # ~2GB, adjust for your image

          # Step 2: Write Ignition config (or use ignition.config.url)
          - name: write-ignition
            image: quay.io/tinkerbell/actions/writefile:v1.0.0
            timeout: 60
            environment:
              DEST_DISK: /dev/sda
              FS_TYPE: ext4
              DEST_PATH: /ignition.json
              CONTENTS: |
                {
                  "ignition": {"version": "3.4.0"},
                  "storage": {"files": []},
                  "systemd": {"units": []}
                }

          # Step 3: Reboot into Flatcar
          - name: reboot-to-flatcar
            image: ghcr.io/jacobweinstock/waitdaemon:v0.0.2
            timeout: 90
            pid: host
```

> **✨ Best Practice:** Instead of `writefile`, use `ignition.config.url` pointing to hegel. Flatcar will fetch Ignition on every boot, making it more resilient:
> ```yaml
> actions:
>   - name: set-ignition-url
>     image: appropriate/curl
>     command: ["sh", "-c"]
>     args: ["echo 'IGNITION_URL=http://10.80.0.1:50060/metadata/{{.HardwareID}}' > /run/ignition-url"]
> ```

### 6C. Workflow CRD

```yaml
# fluxcd/01-infrastructure/tinkerbell/workflow-node01.yaml
apiVersion: tinkerbell.org/v1alpha1
kind: Workflow
metadata:
  name: node01-flatcar
  namespace: tinkerbell
spec:
  templateRef: flatcar-k8s
  hardwareRef: node01
  hardwareMap:
    device_1: aa:bb:cc:dd:ee:01
```

---

## Step 7: Provision First Flatcar Node

### 7A. Apply CRDs

```bash
kubectl apply -f hardware-node01.yaml -f workflow-node01.yaml
```

### 7B. Power On Node

Manually power on the bare-metal node with MAC `aa:bb:cc:dd:ee:01`.

### 7C. Monitor Workflow

```bash
# Watch workflow status
kubectl get workflow -n tinkerbell -w

# View workflow details
kubectl describe workflow node01-flatcar -n tinkerbell

# View task logs
kubectl get tasks -n tinkerbell
kubectl logs -n tinkerbell <task-pod-name>
```

### 7D. Verify Flatcar Boot

```bash
# SSH into the node (if Ignition config includes SSH keys)
ssh core@192.168.20.21

# Check Flatcar version
cat /etc/flatcar/current

# Verify Ignition applied
journalctl -u ignition-firstboot
```

**✅ Success Criteria:**
- [ ] Workflow completes successfully
- [ ] Node boots Flatcar
- [ ] Ignition config applied
- [ ] Node reaches expected state

---

## Step 8: Disable Re-PXE After Successful Provisioning

Prevent nodes from re-entering PXE boot after successful provisioning.

### 8A. Update Hardware CRD

```yaml
# Patch hardware to disable PXE after workflow completes
apiVersion: tinkerbell.org/v1alpha1
kind: Hardware
metadata:
  name: node01
  namespace: tinkerbell
spec:
  interfaces:
    - dhcp:
        mac: aa:bb:cc:dd:ee:01
        # ... existing config ...
      netboot:
        allowPXE: false    # Disable PXE
        allowWorkflow: false  # Disable workflow
```

### 8B. Automate with Kustomize Patch

```yaml
# fluxcd/01-infrastructure/tinkerbell/patch-disable-pxe.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: tinkerbell-hardware
  namespace: tinkerbell
spec:
  path: ./hardware
  sourceRef:
    kind: GitRepository
    name: flux-system
  patches:
    - patch: |-
        - op: replace
          path: /spec/interfaces/0/netboot/allowPXE
          value: false
      target:
        kind: Hardware
        labelSelector: "tinkerbell.org/provisioned=true"
```

**Alternative:** Use a Tinkerbell Hook to disable PXE at the end of the workflow.

---

## Step 9: Scale to Additional Nodes

### 9A. Add Hardware for Each Node

```yaml
# hardware-node02.yaml
apiVersion: tinkerbell.org/v1alpha1
kind: Hardware
metadata:
  name: node02
  namespace: tinkerbell
spec:
  disks:
    - device: /dev/sda
  interfaces:
    - dhcp:
        mac: aa:bb:cc:dd:ee:02
        ip:
          address: 192.168.20.22
          netmask: 255.255.255.0
          gateway: 192.168.20.1
        hostname: node02
      netboot:
        allowPXE: true
        allowWorkflow: true
  metadata:
    instance:
      id: aa:bb:cc:dd:ee:02
```

### 9B. Create Workflow for Each Node

```yaml
# workflow-node02.yaml
apiVersion: tinkerbell.org/v1alpha1
kind: Workflow
metadata:
  name: node02-flatcar
  namespace: tinkerbell
spec:
  templateRef: flatcar-k8s
  hardwareRef: node02
  hardwareMap:
    device_1: aa:bb:cc:dd:ee:02
```

### 9C. Power On Nodes Sequentially

Power on nodes one at a time to avoid overwhelming the provisioning system.

**✅ Success Criteria:**
- [ ] All nodes provisioned successfully
- [ ] All nodes boot Flatcar
- [ ] All nodes have Ignition applied

---

## Step 10: Bootstrap Kubernetes on Flatcar

Deploy Kubernetes on the provisioned Flatcar nodes.

### 10A. Choose Installation Method

| Method | Complexity | Recommendation |
|---|---|---|
| **k3s** | Low | Single binary, systemd unit, ideal for immutable OS |
| **RKE2** | Low | Similar to k3s, Enterprise support |
| **Typhoon** | Medium | Reference Flatcar + K8s, Terraform-based |
| **kubeadm** | High | Manual systemd units, more control |

### 10B. Example: k3s with Ignition

```json
{
  "ignition": {"version": "3.4.0"},
  "storage": {
    "files": [
      {
        "path": "/etc/rancher/k3s/config.yaml",
        "contents": {
          "source": "data:text/plain;base64,Y29uZmlnOiB7CiAgICB0b2tlbi1zZXJ2ZXI6CiAgICAgICAgZmxhdDogc2VydmVyCiAgICAgICAgIGF1dGhzOiB7CiAgICAgICAgICAgICBjbGV0LWNlcnRzOiB0cnVlCiAgICAgICAgICAgICAgICAgY2VydC1tYW5hZ2VyOiB0cnVlCiAgICAgICAgICAgICAgICAgc2VydmVyLWhvc3QtbmFtZTogJ3RpbmtlcmJlbGwtcHJpdmF0ZScKICAgICAgICAgICAgICAgICBzZXJ2ZXItcG9kLWNpZHJzOiAiMTAuMjQuMC4wLzI0IgogICAgICAgICAgICAgICAgIHNlcnZlci1wYWl2ZS10b2tlbi1rZW5lOiAiYWRtaW5pcyIKICAgICAgICAgICAgICAgICBzZXJ2ZXIuaGF2ZS1zY2hlZHVsZXJlOiB0cnVlCiAgICAgICAgICAgICAgICAgc2VydmVyLWt1YmVybmV0ZXM6CiAgICAgICAgICAgICAgICAgICAgIGt1YmUtYXBpLXNlcnZlci1hZGRyZXNzOiAiaHR0cDovLzEwLjgwLjAuMTo2NDQzIgogICAgICAgICAgICAgICAgICAgICBzdWJuZXQtbG9hZC1iYWxhbmNlci1pcDogdHJ1ZQogICAgICAgICAgICAgICAgICAgICB0b2tlbi1zZXJ2ZXItdHJ1c3RlZC1jYWxzOiB0cnVlCiAgICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgfQogICAgICAgICB9"
        }
      }
    ]
  },
  "systemd": {
    "units": [
      {
        "name": "k3s.service",
        "enabled": true,
        "contents": "[Unit]\nDescription=Lightweight Kubernetes\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=notify\nEnvironmentFile=/etc/rancher/k3s/config.yaml\nExecStartPre=-/sbin/modprobe overlay\nExecStartPre=-/sbin/modprobe br_netfilter\nExecStart=/usr/local/bin/k3s server\nKillMode=process\nDelegate=yes\n# Having non-zero Limit*s causes performance problems due to\n# kernel bugs\nLimitNOFILE=infinity\nLimitNPROC=infinity\nLimitCORE=infinity\nTasksMax=infinity\nTimeoutStartSec=0\nRestart=always\nRestartSec=5s\n\n[Install]\nWantedBy=multi-user.target"
      }
    ]
  }
}
```

### 10C. Form the Cluster

For multi-node clusters:

1. **First node (control plane):**
   - Boot with `k3s server --cluster-init`
   - Extract node token: `cat /var/lib/rancher/k3s/server/node-token`

2. **Additional nodes (workers or HA control planes):**
   - Join with: `k3s agent --server https://<first-node-ip>:6443 --token <token>`

3. **Verify cluster:**
   ```bash
   kubectl get nodes
   kubectl get pods -A
   ```

### 10D. Connect Provisioned Cluster to Provisioning Cluster (Optional)

If the provisioned cluster needs to communicate with the bootstrap cluster (e.g., for artifact serving):

```yaml
# On bootstrap cluster, allow traffic from bare-metal VLAN
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: allow-baremetal-to-tinkerbell
  namespace: tinkerbell
spec:
  endpointSelector: {}
  ingress:
    - fromEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: tinkerbell
      toPorts:
        - ports:
            - port: "80"
              protocol: TCP
            - port: "8080"
              protocol: TCP
            - port: "69"
              protocol: UDP
```

**✅ Success Criteria:**
- [ ] Kubernetes control plane running
- [ ] All nodes joined the cluster
- [ ] `kubectl get nodes` shows all nodes Ready

---

## Validation Checklist (Execution Order)

Run through this checklist after completing all steps:

### Network Connectivity
- [ ] `ping 10.80.0.1` from bare-metal VLAN succeeds
- [ ] `traceroute 10.80.0.1` from bare-metal VLAN shows path via relay router
- [ ] Relay router has route to 10.80.0.0/29 (via BGP or static)
- [ ] No ACL/firewall blocks UDP 67, 68, 69 or TCP 80 between VLANs

### BGP & LoadBalancer
- [ ] `kubectl get svc -n tinkerbell` shows smee with External IP 10.80.0.1
- [ ] `cilium bgp routes` (on a Cilium pod) lists 10.80.0.1
- [ ] `kubectl get CiliumBGPAdvertisement -n tinkerbell` shows active advertisement

### DHCP & PXE
- [ ] tcpdump on bare-metal VLAN shows DISCOVER → relay → OFFER from 10.80.0.1
- [ ] DHCP OFFER includes PXE options (next-server=10.80.0.1, filename="ipxe boot script")
- [ ] TFTP request for iPXE binary succeeds
- [ ] HTTP request for iPXE script to 10.80.0.1 succeeds

### Provisioning
- [ ] Workflow CRD status: Completed
- [ ] Node boots Flatcar (check `cat /etc/flatcar/current`)
- [ ] Ignition applied (check `journalctl -u ignition-firstboot`)
- [ ] Disk image written correctly (`lsblk`, `fdisk -l`)

### Post-Provisioning
- [ ] Node does NOT re-PXE on reboot (`allowPXE: false` verified)
- [ ] Kubernetes components running (`systemctl status k3s` or equivalent)
- [ ] Node appears in cluster (`kubectl get nodes`)

---

## Common Failure Modes & Debugging

| Symptom | Likely Cause | Debug Steps |
|---|---|---|
| Node stuck at "PXE-E53: No boot filename received" | DHCP OFFER missing PXE options | Check smee logs, verify relay points to 10.80.0.1 |
| Node gets IP but can't load iPXE | TFTP not reachable | `tcpdump port 69` on smee pod |
| TFTP times out | MTU mismatch on routed path | Check MTU end-to-end, set `ip link set mtu 1500` |
| HTTP 404 for iPXE script | Artifact not hosted | `curl http://10.80.0.1:8080/ipxe-script` |
| DHCP DISCOVER not forwarded | Relay misconfigured | `tcpdump port 67` on relay router |
| DISCOVER forwarded but no OFFER | smee not receiving | Check smee logs, verify `giaddr` subnet matches smee DHCP config |
| OFFER sent but node doesn't get it | Return path blocked | Check firewall on return path |
| Workflow stuck | Action container issue | `kubectl describe task`, check action image pull |
| Node re-PXEs after provisioning | `allowPXE: true` still set | Update Hardware CRD to disable |
| Disk not found | Wrong device path | Check `lsblk` on target node, update Hardware CRD |

### Key Debug Commands

```bash
# smee logs (DHCP/TFTP/HTTP)
kubectl logs -n tinkerbell -l app.kubernetes.io/component=smee -f

# tink logs (workflow engine)
kubectl logs -n tinkerbell -l app.kubernetes.io/component=tink -f

# hegel logs (metadata)
kubectl logs -n tinkerbell -l app.kubernetes.io/component=hegel -f

# Port-forward for local testing
kubectl port-forward -n tinkerbell svc/smee 8080:80
kubectl port-forward -n tinkerbell svc/hegel 50060:50060

# Check smee DHCP config
kubectl get configmap -n tinkerbell smee-config -o yaml

# Capture on relay router
tcpdump -i <iface> -n 'host 10.80.0.1 and (port 67 or port 68)'
```

---

## Bill of Materials

| Component | Version | Source | Purpose |
|---|---|---|---|
| Tinkerbell Helm Chart | 0.20.0+ | oci://ghcr.io/tinkerbell/charts/tinkerbell | Core provisioning stack |
| Cilium | 1.15.x+ | Helm | CNI with BGP |
| Flatcar | 3760.2.0+ | https://flatcar-linux.org | Target OS |
| smee | Bundled | Handles DHCP/PXE/HTTP |
| tink | Bundled | Workflow engine |
| hegel | Bundled | Metadata service |
| oci2disk action | v1.0.0 | quay.io/tinkerbell/actions/oci2disk | Stream OS image |
| writefile action | v1.0.0 | quay.io/tinkerbell/actions/writefile | Write Ignition |
| waitdaemon action | v0.0.2 | ghcr.io/jacobweinstock/waitdaemon | Reboot helper |

---

## References

- [Tinkerbell Documentation](https://tinkerbell.org/docs/)
- [Tinkerbell Helm Chart](https://github.com/tinkerbell/charts)
- [Flatcar Documentation](https://docs.flatcar-linux.org/)
- [Typhoon (Flatcar + K8s)](https://github.com/poseidon/typhoon)
- [Cilium BGP LoadBalancer](https://docs.cilium.io/en/stable/network/loadbalancing/bgp/)
- [DHCP Relay RFC 1542](https://tools.ietf.org/html/rfc1542)

---

## Next Steps

1. **Execute Step 0** — Run the tcpdump to detect existing DHCP server
2. **Finalize DHCP mode** — Set `smee.dhcp.mode` to `full` or `proxy` accordingly
3. **Configure relay** — Update gateway router with correct helper-address(es)
4. **Create GitOps repo** — Commit all manifests to Gitea for Flux reconciliation
5. **Test with single node** — Validate end-to-end before scaling

---

*Generated: 2026-06-21  
Last Updated: 2026-06-21  
Owner: Infrastructure Team  
Status: Ready for Step 0 Execution*
