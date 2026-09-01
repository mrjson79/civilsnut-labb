# Flatcar cluster upgrade — day-2 runbook (Phase 4)

Upgrades the four-node labb cluster in place — no re-imaging, no PXE. End
state: nodeagent `2026-08-30`, Cilium `v1.20.1` hosting the control-plane VIP
(kube-vip retired), Kubernetes `v1.37.0`, and the flatcarctl portal + IAM
stack (Dex + OpenFGA) live at `https://192.168.1.160/`.

Everything is driven from the flatcarctl `ClusterVersion` CRD except two
deliberate manual steps: the one-time drop-in that points the old agents at
the sysext mirror (Phase 3), and kube-vip retirement (Phase 5 — the automated
migration path only covers flannel clusters, not this cilium+kube-vip bake).

Current state (verified 2026-09-01):

| Node           | IP            | Role          | nodeagent  |
|----------------|---------------|---------------|------------|
| flatcar-ctrl-1 | 192.168.1.219 | seed          | 2026-07-03 |
| flatcar-ctrl-2 | 192.168.1.81  | control-plane | 2026-07-03 |
| flatcar-ctrl-3 | 192.168.1.146 | control-plane | 2026-07-03 |
| flatcar-wrk-1  | 192.168.1.212 | worker        | 2026-07-03 |

Kubernetes v1.36.2, Cilium v1.19.5 (kube-proxy-free, L2 announcements OFF),
containerd 2.1.5, VIP `192.168.1.150` on a kube-vip static pod. All nodes are
already on the agent-as-sysext layout (`/etc/extensions/nodeagent.raw`
present), so no bare-binary migration is needed. The `ClusterVersion` CRD is
installed but **no `cluster` object exists yet** — Phase 3 creates it.

Why this exact order: the live CRD only knows the
`flannel/kubeVip/kubernetes/nodeagent` axes, so the nodeagent must roll first
(it re-applies its embedded CRD with the `cilium/portal/iam` axes). Cilium
must roll before kube-vip retirement (the new sysext carries the VIP
manifests and enables L2 announcements). Portal/IAM come last — their L2
LoadBalancer addresses need the new Cilium.

Build host: this Mac (`192.168.2.51`), repo `~/labb/flatcarctl`, branch
`main` (PR #65 is merged — do **not** check out a feature branch). Tooling:
Go + make, podman, squashfs-tools, openssl, `gh` authed to
`anderocloud/flatcarctl`, network for the pinned Dex/OpenFGA source builds.

---

## Phase 0 — preflight

```bash
# Admin kubeconfig for the labb cluster (server already points at the VIP):
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
  'sudo cat /etc/kubernetes/admin.conf' > ~/.kube/labb.config
export KUBECONFIG=~/.kube/labb.config

kubectl get nodes          # 4 nodes, all Ready
kubectl get clusterversion # "No resources found" is the expected answer today
```

Do not proceed with any phase while a previous roll is mid-flight or Halted:
`kubectl get clusterversion cluster -o wide` (once it exists) and
`~/labb/flatcarctl/flatcarctl upgrade status`.

## Phase 1 — build and collect the five sysexts

All in `~/labb/flatcarctl` on `main`:

```bash
make build build-dex build-openfga
# -> bin/nodeagent-x86-64, bin/portal-x86-64, bin/portal-version,
#    bin/dex-x86-64, bin/openfga-x86-64
```

Portal + IAM sysexts (never published as release assets — always baked
locally). `FLATCARCTL_PORTAL_ADDRESS` is required for **both** bakes and is
folded into the sysext cache key; it becomes the console's L2-announced
LoadBalancer /32, the cert SAN, and the OIDC issuer host:

```bash
cd third_party/sysext-bakery
export FLATCARCTL_PORTAL_ADDRESS=192.168.1.160
PORTAL_VER=$(cat ../../bin/portal-version)          # 2026-08-30
./bakery.sh create portal "$PORTAL_VER" --output-file "portal-${PORTAL_VER}-x86-64.raw"
./bakery.sh create iam v2.45.1 --output-file "iam-dex-v2.45.1+openfga-v1.19.0-x86-64.raw"
cd ../..
```

The IAM fetch name is the **composed** version — `dex-v2.45.1+openfga-v1.19.0`,
`+` and all, not the Dex tag. A mis-named IAM asset is the most likely
activation failure.

Nodeagent sysext (no bakery recipe — the standard four-line wrap):

```bash
VER=$(cat bin/portal-version)                       # 2026-08-30 — same VERSION
# stamp as the nodeagent (bin/nodeagent-x86-64 is a Linux binary; it cannot
# run on the macOS build host to report its own version)
stage=$(mktemp -d)
mkdir -p "$stage/usr/bin" "$stage/usr/lib/extension-release.d"
install -m0755 bin/nodeagent-x86-64 "$stage/usr/bin/nodeagent"
printf 'ID=_any\nARCHITECTURE=x86-64\n' > "$stage/usr/lib/extension-release.d/extension-release.nodeagent"
mksquashfs "$stage" "nodeagent-${VER}-x86-64.raw" -all-root -noappend
```

Kubernetes + Cilium come straight from the latest image release:

```bash
gh release download image-2026-08-30.1 -R anderocloud/flatcarctl \
  -p 'cilium-v1.20.1-x86-64.raw' -p 'kubernetes-v1.37.0-x86-64.raw'
```

Five files total: `nodeagent-2026-08-30-x86-64.raw`,
`portal-2026-08-30-x86-64.raw`, `iam-dex-v2.45.1+openfga-v1.19.0-x86-64.raw`,
`cilium-v1.20.1-x86-64.raw`, `kubernetes-v1.37.0-x86-64.raw`.

## Phase 2 — load the mirror (osie nginx on wrk-01)

The nodes will fetch from the Tinkerbell osie file server at
`http://192.168.1.141:7173` — same server that streamed the install image, so
reachability is proven. Note the fetch path does no checksum or signature
verification; this stays a trusted-LAN-only mirror.

1. The Talos kubeconfig is currently broken (omni OIDC issuer mismatch:
   client says `civilsnut.omni.siderolabs.io`, provider answers
   `civilsnut.na-west-1.omni.siderolabs.io`). Repair first:
   `omnictl kubeconfig --force` (or fix the issuer URL in the kubeconfig's
   exec args). Fallback if it stays broken: serve from this Mac instead —
   `python3 -m http.server 8080` in the artifacts dir and use
   `http://192.168.2.51:8080` as the base URL everywhere below (requires
   UniFi to allow 192.168.1.0/24 → 192.168.2.51:8080).
2. Make room. The `hook-artifacts` PVC is 4Gi with ~2.1G used; the five raws
   add ~1.5–2G. Either delete the re-downloadable stock image from the PVC,
   or grow it GitOps-style (bump `01-infrastructure/tinkerbell/hookos-pvc.yaml`
   to 10Gi, commit, reconcile — check `ceph-block` has
   `allowVolumeExpansion: true` first).
3. Copy the raws in via the osie pod (single replica, pinned to wrk-01):
   ```bash
   OSIE=$(kubectl -n tinkerbell get pod -l app.kubernetes.io/name=osie -o name | head -1)
   for f in nodeagent-2026-08-30-x86-64.raw portal-2026-08-30-x86-64.raw \
            'iam-dex-v2.45.1+openfga-v1.19.0-x86-64.raw' \
            cilium-v1.20.1-x86-64.raw kubernetes-v1.37.0-x86-64.raw; do
     kubectl -n tinkerbell cp "$f" "${OSIE#pod/}:/artifacts/$f"
   done
   ```
   (Confirm the mount path with `kubectl -n tinkerbell describe pod` if
   `/artifacts` is wrong; exact filenames matter, `+` included.)
4. **Gate** — from a cluster node, all five answer 200:
   ```bash
   ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
     'for f in nodeagent-2026-08-30-x86-64.raw portal-2026-08-30-x86-64.raw \
               iam-dex-v2.45.1%2Bopenfga-v1.19.0-x86-64.raw \
               cilium-v1.20.1-x86-64.raw kubernetes-v1.37.0-x86-64.raw; do
        curl -so /dev/null -w "%{http_code} $f\n" "http://192.168.1.141:7173/$f"; done'
   ```
   If the URL-encoded `%2B` name 404s but the literal `+` works (or vice
   versa), keep whichever the nginx serves — the agent requests the literal
   composed name.

## Phase 3 — enable orchestration, roll the nodeagent

The 2026-07-03 agents predate the retirement of `FEATURE_UPGRADE_ORCHESTRATION`
(removed 2026-08-17), so they still need the flag ON to act on the CRD at all
— and they have no mirror URL. One drop-in fixes both. **On all four nodes:**

```bash
for n in 192.168.1.219 192.168.1.81 192.168.1.146 192.168.1.212; do
  ssh -i ~/labb/omni/fluxcd/flatcar core@$n '
    sudo mkdir -p /etc/systemd/system/nodeagent.service.d
    printf "[Service]\nEnvironment=FLATCARCTL_SYSEXT_BASE_URL=http://192.168.1.141:7173\nEnvironment=FEATURE_UPGRADE_ORCHESTRATION=on\n" \
      | sudo tee /etc/systemd/system/nodeagent.service.d/10-upgrade.conf >/dev/null
    sudo systemctl daemon-reload && sudo systemctl restart nodeagent'
done
```

**Crash-loop guard, seed only.** After its self-upgrade the new agent runs
`ensureCiliumVIP()`; on this cluster (`cni: cilium`, VIP set) the old cilium
sysext has no `cilium-vip.yml` template, and template-missing + marker-absent
is a hard error that would crash-loop the seed agent mid-roll
(`internal/nodeagent/ciliumvip.go`). With the marker present it degrades to a
logged warning, and the Phase-4 cilium roll (which brings the real template)
triggers the real apply via fingerprint mismatch:

```bash
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
  "sudo sh -c 'mkdir -p /var/lib/nodeagent && echo placeholder > /var/lib/nodeagent/cilium-vip-applied'"
```

Create the ClusterVersion (there is none — `kubectl patch` would fail). The
target must byte-equal `bin/nodeagent-x86-64 --version`:

```bash
kubectl apply -f - <<'EOF'
apiVersion: flatcarctl.anderocloud.com/v1alpha1
kind: ClusterVersion
metadata:
  name: cluster
spec:
  target:
    nodeagent: "2026-08-30"
EOF
```

One leased drain + sysext swap + reboot per node, seed → control planes →
worker. Watch:

```bash
~/labb/flatcarctl/flatcarctl upgrade status
kubectl get nodes -o custom-columns='NODE:.metadata.name,AGENT:.metadata.annotations.flatcarctl\.anderocloud\.com/running-nodeagent'
```

**Gates before Phase 4:**

```bash
# all four report 2026-08-30 (command above), and:
kubectl get crd portalrolebindings.flatcarctl.anderocloud.com   # exists
kubectl explain clusterversion.spec.target.portal               # resolves
kubectl explain clusterversion.spec.target.cilium               # resolves
# seed agent healthy — expect at most the "cilium VIP manifests are applied
# but the baked template is unreadable" warning, no crash loop:
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 'journalctl -u nodeagent -n 20 --no-pager'
```

## Phase 4 — roll Cilium v1.19.5 → v1.20.1

```bash
kubectl patch clusterversion cluster --type merge -p '{"spec":{"target":{"cilium":"v1.20.1"}}}'
```

Sequence the agent executes: each node (seed first) fetches
`cilium-v1.20.1-x86-64.raw`, drains, swaps, reboots. On the seed's
post-reboot resume it applies the VIP manifests (LB-IPAM pool `.150/32` + L2
announcement policy + apiserver LB Service) — these are **inert** while the
running Cilium config still has L2 announcements off. Once all four nodes
converge, the seed re-applies the Cilium DaemonSet/config
(`maybeApplyCiliumManifest`), which turns L2 announcements on. From that
moment until Phase 5 completes, kube-vip and Cilium both answer ARP for
`.150` — both paths reach a working apiserver, so expect at most brief
connection resets, not an outage. Don't linger: do Phase 5 right after the
gate passes.

**Gates:**

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,CILIUM:.metadata.annotations.flatcarctl\.anderocloud\.com/running-cilium'
kubectl get ciliumloadbalancerippools,ciliuml2announcementpolicies
kubectl -n kube-system get pods | grep cilium    # all Running, new generation
kubectl --server https://192.168.1.150:6443 get nodes   # VIP answers
```

## Phase 5 — retire kube-vip (manual, deliberate)

No CRD axis does this: the automated teardown only exists inside the
flannel-cluster migration path. One control plane at a time
(ctrl-1 → ctrl-2 → ctrl-3), verifying the VIP after each:

```bash
for n in 192.168.1.219 192.168.1.81 192.168.1.146; do
  ssh -i ~/labb/omni/fluxcd/flatcar core@$n \
    'sudo rm /etc/kubernetes/manifests/kube-vip.yaml && sudo rm -f /etc/extensions/kube-vip.raw'
  sleep 15
  kubectl --server https://192.168.1.150:6443 get nodes >/dev/null && echo "$n done, VIP OK"
done
```

(Removing the manifest stops the static pod; the sysext symlink removal is
hygiene — the merged image keeps working until next reboot, after which the
kube-vip files simply stop existing.)

**Gates:** `kubectl -n kube-system get pods | grep kube-vip` → empty; VIP
still answers (now Cilium-only); `arping -c3 192.168.1.150` from another LAN
host shows a single stable MAC.

## Phase 6 — roll Kubernetes v1.36.2 → v1.37.0

One minor, no intermediate hops. The mirror already serves
`kubernetes-v1.37.0-x86-64.raw`.

```bash
kubectl patch clusterversion cluster --type merge -p '{"spec":{"target":{"kubernetes":"v1.37.0"}}}'
```

Leased kubeadm-ordered roll, one node at a time, ~4 reboots. Watch with
`flatcarctl upgrade status`. **Gate:** `kubectl get nodes` — all four
`v1.37.0`, all Ready.

## Phase 7 — activate portal + IAM (one patch, one cycle)

Declare both axes together — that's the tested path, and both sysexts land in
a single drain/fetch/swap/reboot cycle per node:

```bash
kubectl patch clusterversion cluster --type merge \
  -p '{"spec":{"target":{"portal":"2026-08-30","iam":"dex-v2.45.1+openfga-v1.19.0"}}}'
```

After the seed's post-reboot resume it applies IAM first, then the portal.
In `flatcarctl-system` expect Deployments `flatcarctl-dex`,
`flatcarctl-openfga`, `flatcarctl-portal` and Secret
`flatcarctl-iam-bootstrap`. On a cold seed, Dex registering its own CRDs can
take several minutes (the agent waits up to 10 min for
`passwords.dex.coreos.com` to be Established) — patience before declaring
failure.

Console: `https://192.168.1.160/` (port 80 redirects; Dex on the same IP,
port 5556). Trust both self-signed certs — sign-in visits Dex directly:

```bash
kubectl -n flatcarctl-system get secret flatcarctl-portal-tls -o jsonpath='{.data.tls\.crt}' | base64 -d > portal-ca.pem
kubectl -n flatcarctl-system get secret flatcarctl-dex-tls    -o jsonpath='{.data.tls\.crt}' | base64 -d > dex-ca.pem
```

Bootstrap admin (generated on the seed, shown nowhere else):

```bash
kubectl -n flatcarctl-system get secret flatcarctl-iam-bootstrap -o jsonpath='{.data.admin-password}' | base64 -d
```

Sign in as `admin@flatcarctl.local`. If sign-in fails on the fresh install:
`ssh core@192.168.1.219 'sudo rm /var/lib/nodeagent/iam-applied && sudo systemctl restart nodeagent'`
— every step is idempotent against cluster state.

Grant roles via the console (home → Users & roles) or `PortalRoleBinding`
(subject = the e-mail, lowercase, byte-exact; issuer `dex`). Do not delete
`flatcarctl-bootstrap-admin` until another cluster admin exists.

Known gotchas, inherited from the spec-009 deployment:

- A later portal/iam version bump rolls the sysext but does **not** re-apply
  the bundle. Fix: on the seed
  `sudo rm /var/lib/nodeagent/portal-applied /var/lib/nodeagent/iam-applied && sudo systemctl restart nodeagent`.
- Every portal pod restart signs everyone out (per-process cookie key).
- TokenReview runs with an empty audience: any valid SA token in the cluster
  authenticates (authorization still gates every route).
- The Administration nav entry wants org-scope admin the bootstrap admin
  doesn't hold — use the home page's "Users & roles" link.
- No MFA on the local Dex accounts; treat `192.168.1.160` like the apiserver.

## Phase 8 — persist the new reality (this repo)

1. Add the mirror URL to both Tinkerbell templates' `nodeagent.service` so
   re-provisioned nodes are upgrade-capable from first boot
   (`hardware/template-flatcar-seed.yaml`, `hardware/template-flatcar-join.yaml`):
   ```
   Environment=FLATCARCTL_SYSEXT_BASE_URL=http://192.168.1.141:7173
   ```
   Note the templates still describe the 2026-07 bake (kube-vip,
   `FEATURE_KUBEADM_BOOTSTRAP`). A future re-provision should use a current
   `flatcarctl bake` image — no kube-vip, no feature flags — and drop those
   lines then.
2. Commit the `hookos-pvc.yaml` size change if the PVC was grown in Phase 2.
3. Pre-existing hazard, now sharper: the Talos cluster's mqtt LoadBalancer
   pins `192.168.1.150` (`02-applications/mqtt/manifests/mqtt-loadbalancer.yaml`)
   and its Cilium pool spans `.150–.159` — the same address the Flatcar
   cluster's VIP now L2-announces from Cilium too. Move mqtt to a different
   IP and shrink the pool block in a follow-up before both sides fight over
   ARP in earnest.

---

Rollback notes: a failed component/agent roll auto-rolls-back and Halts —
resolve with the matching axis reset, never by re-imaging first. The
`flatcarctl` CLI + kubectl remain a complete break-glass path throughout;
nothing in this runbook removes it. Re-provisioning via Tinkerbell
(flip `allowPXE`, reboot) remains the nuclear option and wipes the node.
