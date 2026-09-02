# Flatcar cluster upgrade — day-2 runbook (Phase 4)

Upgrades the four-node labb cluster in place — no re-imaging, no PXE. End
state: nodeagent `2026-08-30`, Cilium `v1.20.1` hosting the control-plane VIP
(kube-vip retired), Kubernetes `v1.37.0`, and the flatcarctl portal + IAM
stack (Dex + OpenFGA) live at `https://192.168.1.160/`.

Everything is driven from the flatcarctl `ClusterVersion` CRD except two
deliberate manual steps: the one-time drop-in that points the old agents at
the sysext mirror (Phase 3), and kube-vip retirement (Phase 5 — the automated
migration path only covers flannel clusters, not this cilium+kube-vip bake).

## Outcome — executed 2026-09-01, complete

Phases 0–7 ran successfully on all four nodes. Verified end state:

| Node           | IP            | Role          | Kubernetes | nodeagent  | cilium  |
|----------------|---------------|---------------|------------|------------|---------|
| flatcar-ctrl-1 | 192.168.1.219 | seed          | v1.37.0    | 2026-08-30 | v1.20.1 |
| flatcar-ctrl-2 | 192.168.1.81  | control-plane | v1.37.0    | 2026-08-30 | v1.20.1 |
| flatcar-ctrl-3 | 192.168.1.146 | control-plane | v1.37.0    | 2026-08-30 | v1.20.1 |
| flatcar-wrk-1  | 192.168.1.212 | worker        | v1.37.0    | 2026-08-30 | v1.20.1 |

`ClusterVersion cluster` reports `UpToDate` with all five axes on target
(portal `2026-08-30`, iam `dex-v2.45.1+openfga-v1.19.0`). Zero kube-vip pods;
`kube-system/kubernetes-vip` holds `192.168.1.150` via Cilium LB-IPAM;
`flatcarctl-portal` + `flatcarctl-dex` answer on `192.168.1.160`.

Two failures worth remembering, neither anticipated by the original plan:

1. **Expired node API credentials stalled the roll before it started.** Agents
   older than flatcarctl `d32acfe` (2026-08-18) mint 24h ServiceAccount tokens
   and never refresh them, so on a 58-day-old cluster every agent logged
   `reconcile: could not read ClusterVersion` / `Unauthorized` and no node ever
   took the lease. Both re-mint paths are no-ops while
   `/etc/nodeagent/kubeconfig` exists, so the fix is to delete it and restart
   the agent on every node (Phase 3 below).
2. **An unexported `KUBECONFIG` sent `kubectl apply` to the local kind
   cluster**, which failed with "no matches for kind ClusterVersion". Pass
   `--kubeconfig` explicitly, or verify `kubectl config current-context`
   before any apply.

The starting state, for reference: Kubernetes v1.36.2, Cilium v1.19.5
(kube-proxy-free, L2 announcements OFF), containerd 2.1.5, nodeagent
2026-07-03, VIP on a kube-vip static pod, no `ClusterVersion` object. All
nodes were already on the agent-as-sysext layout
(`/etc/extensions/nodeagent.raw` present), so no bare-binary migration was
needed.

Why this exact order: the live CRD only knows the
`flannel/kubeVip/kubernetes/nodeagent` axes, so the nodeagent must roll first
(it re-applies its embedded CRD with the `cilium/portal/iam` axes). Cilium
must roll before kube-vip retirement (the new sysext carries the VIP
manifests and enables L2 announcements). Portal/IAM come last — their L2
LoadBalancer addresses need the new Cilium.

Build host: this Mac (`192.168.2.51`), repo `~/labb/flatcarctl`, branch
`main` (PR #65 is merged — do **not** check out a feature branch). Tooling:
Go + make, squashfs-tools (`brew install squashfs`), openssl, `gh` authed to
`anderocloud/flatcarctl`, network for the pinned Dex/OpenFGA source builds,
and a container builder: podman, or docker (OrbStack) through the
`hack/podman-docker-shim/podman` shim — the bakery's Containerfiles are
`FROM scratch` + `COPY` only, and docker's saved archives carry both the
docker-archive and OCI markers, so the nodes' `ctr images import` accepts
them.

---

## Phase 0 — preflight

Kubeconfigs already exist in `~/labb/omni/`: `andero-kubeconfig-lan` (Flatcar
cluster via the seed, `192.168.1.219` — works from this Mac),
`andero-kubeconfig` (via the VIP — does **not** work from this Mac, see
below), and `labbet-kubeconfig.yaml` (Talos cluster via the region-qualified
omni endpoint — the non-region endpoint in `~/.kube/config` is the one with
the broken OIDC issuer).

```bash
export KUBECONFIG=~/labb/omni/andero-kubeconfig-lan
kubectl get nodes
kubectl get clusterversion
```

Expected: 4 nodes Ready; `get clusterversion` answers "No resources found".

Two consequences of going via the seed IP: `kubectl` blips for a minute
whenever the seed itself reboots during a roll (harmless — re-run the watch),
and every VIP-reachability gate below must run **from a node**, not from this
Mac — `192.168.1.150` is unreachable from other VLANs today because the Talos
cluster's mqtt LoadBalancer L2-announces the same address (verified
2026-09-01: `dial tcp 192.168.1.150:6443: i/o timeout` from the Mac while
nodes reach it fine).

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

The `echo` must print `2026-08-30` before the bakes run (an empty
`PORTAL_VER` fails the create with "missing mandatory <version>"):

```bash
export PATH="$HOME/labb/flatcarctl/hack/podman-docker-shim:$PATH"
cd third_party/sysext-bakery
export FLATCARCTL_PORTAL_ADDRESS=192.168.1.160
PORTAL_VER=$(cat ../../bin/portal-version)
echo "$PORTAL_VER"
./bakery.sh create portal "$PORTAL_VER" --output-file "portal-${PORTAL_VER}-x86-64.raw"
./bakery.sh create iam v2.45.1 --output-file "iam-dex-v2.45.1+openfga-v1.19.0-x86-64.raw"
cd ../..
```

The IAM fetch name is the **composed** version — `dex-v2.45.1+openfga-v1.19.0`,
`+` and all, not the Dex tag. A mis-named IAM asset is the most likely
activation failure.

Nodeagent sysext (no bakery recipe — the standard four-line wrap). The
version comes from `bin/portal-version`: it is the same repo-wide VERSION
stamp the nodeagent carries, and `bin/nodeagent-x86-64` is a Linux binary
that cannot run on the macOS build host to report its own:

```bash
VER=$(cat bin/portal-version)
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

1. Talos cluster access: use `~/labb/omni/labbet-kubeconfig.yaml` (the
   region-qualified omni endpoint; verified working). Fallback if Talos
   access breaks: serve from this Mac instead —
   `python3 -m http.server 8080` in the artifacts dir and use
   `http://192.168.2.51:8080` as the base URL everywhere below (requires
   UniFi to allow 192.168.1.0/24 → 192.168.2.51:8080).
2. Make room. The file server is the **hookos** pod's `hookos` (nginx)
   container; the `hook-artifacts` PVC is mounted at `/usr/share/nginx/html`
   (verified 2026-09-01: 3.9G volume, 3.5G used, 451M free — the five raws
   total ~680M). Deleting the stock Flatcar image (846M, local copy kept at
   `~/flatcar-images/`) frees enough; growing the PVC GitOps-style
   (`hookos-pvc.yaml` → 10Gi) remains the long-term fix.
3. Copy the raws in via the hookos pod (single replica, pinned to wrk-01;
   exact filenames matter, `+` included):
   ```bash
   export TALOS_KC=~/labb/omni/labbet-kubeconfig.yaml
   HOOKOS=$(kubectl --kubeconfig "$TALOS_KC" -n tinkerbell get pod -l app=hookos -o name | head -1)
   kubectl --kubeconfig "$TALOS_KC" -n tinkerbell exec "$HOOKOS" -c hookos -- \
     rm /usr/share/nginx/html/flatcar_production_image_x86-64.bin.zst
   cd ~/sysext-upload
   for f in *.raw; do
     kubectl --kubeconfig "$TALOS_KC" -n tinkerbell cp "$f" \
       "${HOOKOS#pod/}:/usr/share/nginx/html/$f" -c hookos
   done
   ```
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

**Re-mint the node API credentials.** The 2026-07-03 agents mint 24h tokens
and never refresh them (the refresh loop landed 2026-08-18, `d32acfe`), so on
any cluster older than a day the reconcile loop logs
`reconcile: could not read ClusterVersion` / `Unauthorized` and no roll ever
starts. Both re-mint paths are no-ops while `/etc/nodeagent/kubeconfig`
exists, so delete it and restart — the seed re-mints from `admin.conf`, the
rest fetch from the seed's `:9443` broker:

```bash
for n in 192.168.1.219 192.168.1.81 192.168.1.146 192.168.1.212; do
  ssh -i ~/labb/omni/fluxcd/flatcar core@$n \
    'sudo rm -f /etc/nodeagent/kubeconfig && sudo systemctl restart nodeagent'
done
```

Verify with `journalctl -u nodeagent` on the seed: `wrote scoped node
kubeconfig`, and the `could not read ClusterVersion` lines stop. The fresh
tokens last 24h — enough for the nodeagent roll, after which the 2026-08-30
agents refresh their own credentials and this cannot recur.

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
# VIP reachability — from a node, NOT from this Mac (see Phase 0):
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.212 'curl -ks https://192.168.1.150:6443/healthz'  # "ok"
```

## Phase 5 — retire kube-vip (manual, deliberate)

No CRD axis does this: the automated teardown only exists inside the
flannel-cluster migration path. One control plane at a time
(ctrl-1 → ctrl-2 → ctrl-3), verifying the VIP after each:

The VIP check after each removal runs from the (untouched) worker:

```bash
for n in 192.168.1.219 192.168.1.81 192.168.1.146; do
  ssh -i ~/labb/omni/fluxcd/flatcar core@$n \
    'sudo rm /etc/kubernetes/manifests/kube-vip.yaml && sudo rm -f /etc/extensions/kube-vip.raw'
  sleep 15
  ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.212 \
    'curl -ks https://192.168.1.150:6443/healthz' && echo " <- $n done, VIP OK"
done
```

(Removing the manifest stops the static pod; the sysext symlink removal is
hygiene — the merged image keeps working until next reboot, after which the
kube-vip files simply stop existing.)

**Gates:** `kubectl -n kube-system get pods | grep kube-vip` → empty; the
worker's `curl -ks https://192.168.1.150:6443/healthz` still answers "ok"
(now Cilium-only); `arping -c3 192.168.1.150` from a 192.168.1.0/24 host
shows a single stable MAC.

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

## Phase 8 — persist the new reality (this repo) — DONE

Everything above was applied by hand over SSH. These two changes make the
durable parts declarative, so a PXE re-provision produces a node that can
upgrade itself:

1. **Sysext mirror URL in both Tinkerbell templates' `nodeagent.service`**
   (`hardware/template-flatcar-seed.yaml`, `hardware/template-flatcar-join.yaml`):
   ```
   Environment=FLATCARCTL_SYSEXT_BASE_URL=http://192.168.1.141:7173
   ```
   Note for future edits: that unit is a **plain JSON string** inside the
   nested YAML literal block, not a percent-encoded `data:` URL — insert
   literal text with `\n` separators, do not escape `://`, and keep it on one
   line. `FEATURE_UPGRADE_ORCHESTRATION` is deliberately not persisted; only
   the pre-2026-08-17 agents needed it.
2. **`hookos-pvc.yaml` grown 4Gi → 10Gi.** The volume is no longer just
   HookOS + install images — it is the fleet's permanent sysext mirror, and
   4Gi hit 86% during this upgrade.

Verify a change to these templates before committing:

```bash
cd 01-infrastructure/tinkerbell/hardware
for t in seed join; do
  yq -r '.spec.data' template-flatcar-$t.yaml \
    | yq -r '.tasks[0].actions[1].environment.CONTENTS' \
    | jq -r '.systemd.units[0].contents' | grep -E '^(Environment|ExecStart)='
done
```

### Open follow-ups

**Re-bake the install image.** Both templates still stream the 2026-07-04
bake (Kubernetes v1.36.2, cilium v1.19.5, kube-vip v1.2.1, nodeagent
2026-07-03). Re-provisioning any node today rejoins a v1.37.0 cluster with a
kube-vip static pod fighting Cilium for `192.168.1.150` and an agent too old
to refresh its own API credential. Both templates now carry a ⚠️ header
saying so. Fix: `flatcarctl bake` with the current sysext set, publish to the
mirror, update `IMG_URL` in both templates.

**Move mqtt off `192.168.1.150`** (deferred — needs a device-reconfiguration
window). The collision is not just an ARP race: `00-foundation/cilium/config/bgp-peering-policy.yaml`
advertises every `LoadBalancerIP` to UniFi (peer `192.168.1.1` ASN 65510,
local 65512) with an always-true selector, so the router holds a `.150/32`
route pointing at a Talos node. That is why `192.168.1.150:6443` times out
from other VLANs while the nodes themselves reach it fine. Planned fix:
repoint `02-applications/mqtt/manifests/mqtt-loadbalancer.yaml` (annotation
`io.cilium/lb-ipam-ips`) to `192.168.4.13` and drop the `.150–.159` block
from `00-foundation/cilium/config/ippool.yaml` — nothing else in the repo
draws from that block. Cost: re-run `configure-shelly.sh` per device (the
script reads the LB IP live, so it needs no edit, but each device has the old
address in flash) and re-point Home Assistant's MQTT broker host in its UI.
In-cluster clients use `mosquitto.mosquitto.svc.cluster.local` and need
nothing. Until then, reach the apiserver from off-LAN via
`andero-kubeconfig-lan` (seed direct).

---

Rollback notes: a failed component/agent roll auto-rolls-back and Halts —
resolve with the matching axis reset, never by re-imaging first. The
`flatcarctl` CLI + kubectl remain a complete break-glass path throughout;
nothing in this runbook removes it. Re-provisioning via Tinkerbell
(flip `allowPXE`, reboot) remains the nuclear option and wipes the node.
