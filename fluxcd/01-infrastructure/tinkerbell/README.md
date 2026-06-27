# Tinkerbell — bare-metal PXE provisioning (Flatcar)

Provisions bare-metal machines on the lab LAN by PXE-booting them into HookOS,
streaming a Flatcar image to disk, and applying Ignition.

> `plan.md` in this directory is the **original draft** and is superseded by
> these manifests. It was written against an older Tinkerbell chart and is
> wrong on most concrete details (chart version, value keys, DHCP modes, the
> `oci2disk` action, `.bin.gz`). Keep it only as historical context.

## Design (the "why")

- **Chart:** single unified `tinkerbell` chart, **v0.23.0** (latest), as an
  OCI artifact via Flux `OCIRepository` + `chartRef`. smee/tink/tootles/rufio
  are no longer subcharts — everything is configured under
  `deployment.envs.globals` / `deployment.envs.<component>`.
- **Topology = same-L2, `hostNetwork`, proxy DHCP, pinned to one node.**
  - The LAN is flat `192.168.1.0/24` and **UniFi already runs DHCP** (it stays
    authoritative). smee runs in **`dhcpMode: proxy`** — it only adds the PXE
    boot options (next-server + iPXE filename); it does **not** hand out leases.
    Using `reservation` mode would make smee a second authoritative DHCP server
    and start a lease war with UniFi.
  - ProxyDHCP must hear the L2 broadcast DISCOVER, so smee runs with
    `hostNetwork: true` on a node that's on the machine's broadcast domain.
    All Talos nodes are on `192.168.1.0/24`; we **pin** one so `publicIP`
    (the next-server / iPXE host) is stable.
  - No VLAN, no BGP `/29`, no DHCP relay. (That setup — Option B in `plan.md`
    — is for an *isolated provisioning network* or datacenter scale; overkill
    for one machine.)
- **No kube-vip.** The chart bundles kube-vip and defaults
  `service.lbClass: kube-vip.io/kube-vip-class`; on this Cilium LB-IPAM cluster
  that conflicts. We set `optional.kubevip.enabled: false`, `service.type:
  ClusterIP`, and clear `lbClass`. hostNetwork binds the service ports
  (67/udp, 69/udp, 7080, 514/udp) to host ports on the pinned node.
- **HookOS** is downloaded by a sidecar and served by the `osie` nginx
  deployment on `:7173`, also `hostNetwork` on the same pinned node →
  `artifactsFileServer = http://<node IP>:7173`. Backed by a **`ceph-block`
  RWO** PVC (`hookos-pvc.yaml`) — RWX/CephFS is **not** needed because the
  downloader is a sidecar in the single-replica osie pod (CephFS is also
  disabled in this cluster's rook-ceph).

## ⚠️ Before committing — fill three placeholders

All three must point at the **same** Talos node (pinned, on `192.168.1.0/24`):

| Value (`release.yaml`)                         | Set to                       |
|------------------------------------------------|------------------------------|
| `publicIP`                                     | pinned node's LAN IP         |
| `artifactsFileServer` host                     | same node's LAN IP           |
| `deployment.nodeSelector` + `optional.osie.nodeSelector` `kubernetes.io/hostname` | pinned node's hostname (e.g. `wrk-01`) |

Candidate nodes (verify hostname↔IP — repo only documents IPs and names
separately): `wrk-01..04` / `192.168.1.141, .252, .192, .182`.

## Activate (after placeholders are filled)

Add the component to the infrastructure phase so Flux reconciles it:

```yaml
# fluxcd/01-infrastructure/kustomization.yaml → resources:
  - tinkerbell
```

Then commit + push. Verify:
- osie pod `Running` (download sidecar completes), `hook-artifacts` PVC `Bound`
- tinkerbell deployment `Running` on the pinned node, host ports listening
- power on the machine → smee logs show DISCOVER → proxyDHCP offer → TFTP iPXE
  → HTTP iPXE script → HookOS boots

## Phase 2 — Hardware / Template / Workflow (one machine)

Once the stack is healthy and HookOS boots, add `hardware/` with:
- **Hardware** CRD (`tinkerbell.org/v1alpha1`): the machine's NIC MAC, target
  disk, `netboot.allowPXE/allowWorkflow`.
- **Template**: `image2disk` action (**not** `oci2disk`) streaming the Flatcar
  **`.bin.bz2`** image (image2disk auto-decompresses bzip2), then Ignition,
  then reboot.
- **Workflow**: binds template ↔ hardware by MAC.

Inputs still needed to write phase 2:
1. The machine's **NIC MAC address**.
2. **Target disk** device (`/dev/sda` vs `/dev/nvme0n1`).
3. **SSH public key** (+ hostname/role) for the Flatcar Ignition.
4. Flatcar channel/version (default: latest **stable**, ~`4230.x`).
