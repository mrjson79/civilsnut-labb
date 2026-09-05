# Flatcar cluster + portal upgrades — routine runbook

Rolls the four-node labb cluster and the flatcarctl portal/IAM stack forward on
an already-healthy cluster. Everything here is declarative: you publish
artifacts to the mirror, edit one `ClusterVersion` object, and the nodeagents
converge the fleet. No SSH, no re-imaging.

**This is the repeatable procedure.** For the one-time 2026-09-01 migration off
the pre-spec-008 bake (retired feature flag, expired credentials, kube-vip
retirement) see [`flatcar-cluster-upgrade.md`](./flatcar-cluster-upgrade.md) —
none of those steps recur. The authoritative contract behind this runbook is
`~/labb/flatcarctl/docs/upgrade-contract.md`; consult it rather than trusting
this summary when the two disagree.

Baseline this runbook was written against (2026-09-02):

| Axis | Running |
|------|---------|
| kubernetes | v1.37.0 |
| cilium | v1.20.1 |
| portal | 2026-08-30 |
| iam | dex-v2.45.1+openfga-v1.19.0 |
| nodeagent | 2026-08-30 |
| flatcar (OS) | 4593.2.5 |
| network | not installed |

---

## 1. How the machinery works

One cluster-scoped singleton, `ClusterVersion` named `cluster` (short name
`cv`). You write `spec.target.<axis>`; every nodeagent polls on a 30 s tick,
notices drift, and takes a fleet-wide lease (`flatcar-upgrade` in
`kube-system`, 10 min TTL) to drain → swap the sysext → reboot → verify, **one
node at a time, seed → control-plane → worker**.

Seven axes: `kubernetes`, `cilium`, `kubeVirt`, `portal`, `iam`, `network`,
`nodeagent`. (`flatcar`, `containerd`, `flannel`, `kubeVip` and `cni` are
removed — declaring them logs a warning and is ignored.)

Four phases in `status.phase`: `Progressing`, `UpToDate`, `Halted`, `Held`,
plus empty for "nothing declared yet".

**The ordering rule that decides how you batch your patches.** Each node walks
a strict priority ladder and stops at the first thing with work to do:

```
rebootGeneration  >  kubernetes  >  {cilium, kubeVirt, portal, iam, network}  >  nodeagent  >  OS reboot
```

The five component axes in that group share **one** drain/swap/reboot cycle, so
declaring all of them together costs one reboot per node. Anything on a
different rung is a separate full pass over the fleet. Concretely: `kubernetes`
+ `cilium` in one patch is two reboots per node, not one.

---

## 2. Pre-flight gate

```bash
export KUBECONFIG=~/labb/omni/andero-kubeconfig-lan
kubectl config current-context      # must NOT be a kind/OrbStack context
```

Getting this wrong is the most likely wasted hour: an apply against the local
kind cluster fails with `no matches for kind ClusterVersion`, which reads like a
broken CRD. Prefer `kubectl --kubeconfig ~/labb/omni/andero-kubeconfig-lan` in
one-off commands.

```bash
# 1. Fleet is idle and on target — phase must be UpToDate (or empty), never Halted/Held
kubectl get cv cluster -o wide

# 2. Every node Ready, no failure annotations, and note the agent version
kubectl get nodes
kubectl get nodes -o custom-columns='NODE:.metadata.name,\
AGENT:.metadata.annotations.flatcarctl\.anderocloud\.com/running-nodeagent,\
FAILED:.metadata.annotations.flatcarctl\.anderocloud\.com/upgrade-failed'

# 3. Mirror reachable from a node, with room for the new artifacts
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
  'curl -sI http://192.168.1.141:7173/ | head -1'
kubectl --kubeconfig ~/labb/omni/labbet-kubeconfig.yaml -n tinkerbell exec \
  "$(kubectl --kubeconfig ~/labb/omni/labbet-kubeconfig.yaml -n tinkerbell get pod -l app=hookos -o name | head -1)" \
  -c hookos -- df -h /usr/share/nginx/html
```

Three conditions that will bite if you skip them:

- **`running-nodeagent` must be `>= 2026-08-28` on every node** before you touch
  `spec.target.portal` or `spec.target.iam`. The bundle re-apply fix
  (flatcarctl `608c82e`) is agent-side; an older agent on any single node rolls
  the sysext, annotates the new version, and leaves the Deployment on the old
  image indefinitely. Ours are all `2026-08-30`.
- **No un-evictable VMs.** A roll drains every node in turn; the drain timeout
  is 5 minutes, and exceeding it halts the fleet. Stop or live-migrate any
  KubeVirt VM without a workable eviction strategy first.
- **Serving certs should be `CA:FALSE`.** A leaf is left alone across upgrades,
  so browser trust survives. A legacy `CA:TRUE` cert (a key baked into an old
  image) is force-rotated with a pod restart, and every pinned copy must be
  re-trusted.
  ```bash
  kubectl -n flatcarctl-system get secret flatcarctl-dex-tls \
    -o jsonpath='{.data.tls\.crt}' | base64 -d \
    | openssl x509 -noout -text | grep -A1 'Basic Constraints'
  ```
  Both of ours are `CA:FALSE`, valid to 2036.

---

## 3. Choose the target versions

### What's published

`kubernetes`, `containerd`, `cilium`, `kubevirt` (and, from the next image
release onward, `network`) ship as assets on `image-*` GitHub releases.
`nodeagent-*` releases publish **bare binaries, not sysexts** — you wrap those
yourself (§4). **`portal` and `iam` are never published** and are always a local
bake.

```bash
cd ~/labb/flatcarctl && git pull

# Needs gh (install with: brew install gh). It vanished from PATH once
# mid-session, so the fallback below is the reliable one.
gh release list -R anderocloud/flatcarctl --limit 10
gh release view image-2026-08-30.1 -R anderocloud/flatcarctl --json assets -q '.assets[].name'

# Fallback, no gh required:
git ls-remote --tags origin 'refs/tags/image-*'     | sed 's#.*refs/tags/##' | sort -V | tail -5
git ls-remote --tags origin 'refs/tags/nodeagent-*' | sed 's#.*refs/tags/##' | sort -V | tail -3
```

As of 2026-09-02 the newest image release is still `image-2026-08-30.1` — the
same Kubernetes v1.37.0 and cilium v1.20.1 we already run, so those axes have
nothing to do. The newest nodeagent is `nodeagent-2026-09-05.1`.

### Bare tags vs content-qualified

`cilium`, `kubeVirt`, `iam` and `network` accept an optional `+<8 hex>` content
suffix. **A bare tag means "any content of this upstream version"**, so our
bare `v1.20.1` and bare `dex-v2.45.1+openfga-v1.19.0` are deliberate stay-put
declarations — a flatcarctl upgrade alone will never roll them. Naming the
qualified string is what picks up rebuilt payload content.

Derive one with the bakery, which reads the axis's declared content inputs:

```bash
cd ~/labb/flatcarctl/third_party/sysext-bakery
./bakery.sh version cilium v1.20.1     # -> v1.20.1+03a4fbef
./bakery.sh content-hash iam           # -> just the 8 hex characters
```

> ⚠️ **macOS portability.** These used GNU `stat -c` and silently hashed every
> file's size as `0` on macOS, producing a hash no Linux bake would ever match
> (cilium came out as `5de59ac4` instead of `03a4fbef`). Fixed 2026-09-02 in
> `flatcarctl-lib/contentversion.sh`. If you are on a checkout that predates
> that fix, or the output is preceded by `stat: illegal option -- c`, the hash
> is wrong — do not use it. Cross-check against a known-good value
> (`./bakery.sh content-hash cilium` must print `03a4fbef` on an unmodified
> cilium axis) before trusting a freshly derived string.

Independent sources for a qualified version:

1. The **component manifest** in an `image-*` release's notes (verbatim
   `/etc/flatcar-bake-versions.yaml` from that image) — for published axes.
2. A node's live annotation: `flatcarctl.anderocloud.com/running-<axis>`.
3. A node's live version file: `/usr/local/share/<axis>-version`.

**Not** `/etc/flatcar-bake-versions.yaml` on *our* nodes — that is the
bake-time snapshot and is stale on any rolled cluster. Ours still reads
`kubernetes: v1.36.2, cni_version: v1.19.5, kube_vip: v1.2.1` from the July
image.

### Version strings you generate locally

`VERSION` is the git commit date of the checkout, and it stamps both the
nodeagent and the portal:

```bash
cd ~/labb/flatcarctl
git log -1 --format=%cd --date=format:%Y-%m-%d      # this IS the Makefile's expression
```

`bin/portal-version` holds whatever the *last* build stamped, not what the next
one will — currently `2026-08-30` against a `2026-09-05` tree. Use it only to
ask "what are the binaries in `bin/` stamped with".

> **Same-day trap.** The portal version is the commit date, so two bakes on one
> day produce the same string and the second one does not roll. Re-cutting the
> portal on a day you have already baked requires
> `VERSION=YYYY-MM-DD.N make build` *and*
> `FLATCARCTL_PORTAL_VERSION=YYYY-MM-DD.N` on the bake.

---

## 4. Build and publish the artifacts

| Axis | Source |
|------|--------|
| kubernetes, cilium, kubeVirt, network | `gh release download` from an `image-*` release |
| nodeagent | download the release binary (or `make build`), then wrap it with `mksquashfs` yourself |
| portal | `make build` + `bakery.sh create portal` |
| iam | `make build-dex build-openfga` + `bakery.sh create iam` |

```bash
cd ~/labb/flatcarctl
export PATH="$HOME/labb/flatcarctl/hack/podman-docker-shim:$PATH"   # docker instead of podman
make build build-dex build-openfga
```

Portal and IAM sysexts. `FLATCARCTL_PORTAL_ADDRESS` is required for the portal
bake — it becomes the LB-IPAM `/32`, the cert IP SAN, and the Dex issuer, and it
is folded into the bake cache key:

```bash
cd third_party/sysext-bakery
export FLATCARCTL_PORTAL_ADDRESS=192.168.1.160
PORTAL_VER=$(cat ../../bin/portal-version)
echo "$PORTAL_VER"      # sanity-check: must be the version you just built
./bakery.sh create portal "$PORTAL_VER" --output-file "portal-${PORTAL_VER}-x86-64.raw"
./bakery.sh create iam v2.45.1 --output-file "iam-dex-v2.45.1+openfga-v1.19.0-x86-64.raw"
cd ../..
```

Nodeagent sysext — there is no bakery recipe; this is the same four-line wrap
the image builder uses:

```bash
VER=$(cat bin/portal-version)   # same repo-wide VERSION; the Linux binary can't run here to self-report
stage=$(mktemp -d)
mkdir -p "$stage/usr/bin" "$stage/usr/lib/extension-release.d"
install -m0755 bin/nodeagent-x86-64 "$stage/usr/bin/nodeagent"
printf 'ID=_any\nARCHITECTURE=x86-64\n' > "$stage/usr/lib/extension-release.d/extension-release.nodeagent"
mksquashfs "$stage" "nodeagent-${VER}-x86-64.raw" -all-root -noappend
```

### Filename contract

The node builds its fetch URL as `<name>-<version>-<arch>.raw` appended to
`FLATCARCTL_SYSEXT_BASE_URL`, with the version substituted **verbatim — no URL
encoding**. So the `+` in an iam or content-qualified name must be served
literally, and the filename must match `spec.target.<axis>` exactly. A static
mirror does no resolution whatsoever; a wrong name 404s on every tick, gets
logged, and the other axes keep rolling while nothing happens on that one.

### Publish to the mirror

```bash
export TALOS_KC=~/labb/omni/labbet-kubeconfig.yaml
HOOKOS=$(kubectl --kubeconfig "$TALOS_KC" -n tinkerbell get pod -l app=hookos -o name | head -1)
cd ~/sysext-upload      # wherever the .raw files are
for f in *.raw; do
  kubectl --kubeconfig "$TALOS_KC" -n tinkerbell cp "$f" "${HOOKOS#pod/}:/usr/share/nginx/html/$f" -c hookos
done
```

If `kubectl cp` complains about a missing `tar` in the container:

```bash
for f in *.raw; do
  kubectl --kubeconfig "$TALOS_KC" -n tinkerbell exec -i "$HOOKOS" -c hookos -- \
    sh -c "cat > '/usr/share/nginx/html/$f'" < "$f"
done
```

**Gate — every target must return 200 from a node before you write the target:**

```bash
ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
  'for f in <each-filename>; do curl -sgo /dev/null -w "%{http_code} $f\n" "http://192.168.1.141:7173/$f"; done'
```

Note the node performs **no checksum or signature verification** on a fetched
sysext — a truncated download aborts safely, but a substituted file would be
installed. This mirror is trusted because the LAN is.

---

## 5. Roll it

Batch by rung (§1). For a full refresh, three patches with a `UpToDate` gate
between each:

```bash
# Pass 1 — all component axes together: ONE reboot per node
kubectl patch cv cluster --type merge -p '{"spec":{"target":{
  "cilium":"<version>",
  "portal":"<version>",
  "iam":"<composed-version>"
}}}'

# wait for UpToDate, then:
# Pass 2 — Kubernetes (its own rung; one minor at a time if you skip minors)
kubectl patch cv cluster --type merge -p '{"spec":{"target":{"kubernetes":"<version>"}}}'

# wait for UpToDate, then:
# Pass 3 — the agent last, so the whole roll ran under a known agent
kubectl patch cv cluster --type merge -p '{"spec":{"target":{"nodeagent":"<version>"}}}'
```

A merge patch only changes the axes you name, so this never clears the others.
Roll the agent **last**: an agent upgrade mid-sequence changes the code driving
the remaining passes.

Kubernetes is the only axis that multi-hops — the planner walks one minor at a
time, gated on the whole fleet being Ready, and `status.plan` shows the route.
Every intermediate minor must be on the mirror. All other axes are a single
exact-string hop.

If you are bumping KubeVirt and Kubernetes together, bump `kubeVirt` into a
window that covers both the current and next Kubernetes minor **first**, and
let it reach `UpToDate` before walking Kubernetes. Nothing enforces the skew
window; it is documented guidance only.

To reboot the fleet with no version change (kernel arg, sysctl), bump
`spec.rebootGeneration` — on its own, never in the same patch as a version
change, since it outranks every version axis:

```bash
kubectl patch cv cluster --type merge -p '{"spec":{"rebootGeneration":1}}'
```

Strictly increasing values only; `0` is inert, and each node reboots at most
once per generation.

**From the console instead.** An `admin`-on-`cluster` subject can retarget any
axis and trigger the reboot drill at `https://192.168.1.160/api/v1/clusterversion`.
The console form requires an explicit confirm step; the JSON API is bearer-token
only (a cookie is not accepted). Preparing the mirror is not something the
portal can do for you, so §4 still comes first.

---

## 6. Watch it

```bash
~/labb/flatcarctl/flatcarctl upgrade status --kubeconfig ~/labb/omni/andero-kubeconfig-lan
```

> ⚠️ `upgrade status` renders the Kubernetes table plus only the `portal`,
> `iam` and `network` axes. **`cilium`, `kubeVirt` and `nodeagent` never
> appear** — a cilium roll is invisible to this command. Use the annotations
> for those.

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,\
CLASS:.metadata.annotations.flatcarctl\.anderocloud\.com/node-class,\
PHASE:.metadata.annotations.flatcarctl\.anderocloud\.com/reconcile-phase,\
K8S:.metadata.annotations.flatcarctl\.anderocloud\.com/running-kubernetes,\
CILIUM:.metadata.annotations.flatcarctl\.anderocloud\.com/running-cilium,\
PORTAL:.metadata.annotations.flatcarctl\.anderocloud\.com/running-portal,\
IAM:.metadata.annotations.flatcarctl\.anderocloud\.com/running-iam,\
AGENT:.metadata.annotations.flatcarctl\.anderocloud\.com/running-nodeagent,\
OS:.metadata.annotations.flatcarctl\.anderocloud\.com/running-flatcar,\
FAILED:.metadata.annotations.flatcarctl\.anderocloud\.com/upgrade-failed'

kubectl get lease flatcar-upgrade -n kube-system -o jsonpath='{.spec.holderIdentity}{"\n"}'
```

Expect, per pass: one node at a time goes `draining` → `rebooting` →
`verifying` → `idle`, seed first. `kubectl` blips while the seed itself reboots
(this kubeconfig points at the seed) — re-run the watch.

**cilium and kubeVirt converge in two stages.** All nodes reporting the target
annotation is stage one. The seed then re-applies the DaemonSet (or the KubeVirt
CR) *only after* the whole fleet holds the new payload — that is the air-gap
gate. `status.phase` describes the Kubernetes axis only and says nothing about
stage two, so check the workload:

```bash
kubectl -n kube-system get ds cilium -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

---

## 7. When it goes wrong

`status.phase` becomes:

- **`Halted`** — a node failed, auto-reverted its sysext, and came back Ready.
  The fleet is stopped at the old version and no further version leases are
  granted. The cluster is healthy; the roll is not.
- **`Held`** — a node failed and did *not* recover. It keeps the lease and needs
  manual repair (in practice, re-imaging) before anything else moves.

Find the offender:

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,\
FAILED:.metadata.annotations.flatcarctl\.anderocloud\.com/upgrade-failed,\
FAILVER:.metadata.annotations.flatcarctl\.anderocloud\.com/failed-version'
```

**Clearing a halt: edit `spec.target.<the halted axis>` to anything that is not
the offending version** — unset it, or set it back to what the nodes actually
run. There is no `flatcarctl upgrade resume`. The halted node drops its
annotation within one 30 s tick and the seed rewrites the phase on the next, so
allow a minute.

```bash
kubectl patch cv cluster --type merge -p '{"spec":{"target":{"cilium":"v1.20.1"}}}'   # back to running
```

Three traps in the diagnostics:

- **`status.rollingMinor` is overloaded on a component halt.** It will read
  something like `portal 2026-08-28` — a component and version, not a
  Kubernetes minor. The console decodes this; `upgrade status` prints it
  verbatim under a `Rolling:` label.
- **On a batched component roll the halt is recorded against the first axis in
  registry order** (cilium → kubevirt → portal → iam → network), which may not
  be the axis that actually failed. Read the node's journal:
  `ssh core@<node> journalctl -u nodeagent -n 100 --no-pager`.
- **`iam-idp` is a distinct halt**, raised when Dex cannot serve OIDC discovery
  and a non-empty key set within 10 minutes of an IAM roll. Nobody can sign in
  while it stands. It clears by itself once Dex recovers, or immediately if you
  take `spec.target.iam` off that version. Look at
  `kubectl -n flatcarctl-system logs deploy/flatcarctl-dex`.

A drain timeout is the other common halt — nothing was swapped, the node stays
healthy on the old version, and the cause is almost always a pod that will not
evict.

---

## 8. Portal and IAM specifics

- **Every portal or IAM roll signs out every operator.** The session signing key
  is generated per process, so any portal restart invalidates all sessions and
  CSRF tokens. Dex refresh tokens live in etcd, so re-signing-in is usually
  silent, but announce the interruption.
- **What survives:** Dex's signing keys, auth codes and refresh tokens (CRD
  storage in etcd), all `PortalRoleBinding` objects, and the
  `flatcarctl-iam-bootstrap` Secret (created once, never re-applied, so the
  admin password and the portal's OIDC client secret are stable).
- **What is rebuilt:** OpenFGA runs on an in-memory datastore by design. It
  starts empty and the portal rewrites the model and tuples from the
  `PortalRoleBinding` objects within about 10 seconds. Authorization fails
  closed until then. Being OOMKilled is a survivable event for the same reason.
- **Certs are left alone.** Serving certs are minted on the node, not baked, and
  an existing leaf is never rotated — which is also why a real certificate you
  install by hand survives every re-apply:
  ```bash
  kubectl -n flatcarctl-system create secret tls flatcarctl-portal-tls \
    --cert=fullchain.pem --key=privkey.pem --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n flatcarctl-system delete pod -l app=flatcarctl-portal
  ```
  It must include the announced IP as an **IP SAN** and be `CA:FALSE` (a
  `CA:TRUE` cert is treated as a leaked baked key and deleted). Note
  `flatcarctl-dex-tls` is the portal's only trust anchor, so put the full chain
  in `tls.crt` there.
- Retrieve the bootstrap admin password (generated on the seed, printed nowhere):
  ```bash
  kubectl -n flatcarctl-system get secret flatcarctl-iam-bootstrap \
    -o jsonpath='{.data.admin-password}' | base64 -d; echo
  ```
- If the portal or IAM bundle looks stuck at an old image, the marker is
  version-keyed, so the convergent repair is to delete it and restart the agent
  on the seed — but on an agent `>= 2026-08-28` this should never be necessary:
  ```bash
  ssh -i ~/labb/omni/fluxcd/flatcar core@192.168.1.219 \
    'sudo rm /var/lib/nodeagent/portal-applied /var/lib/nodeagent/iam-applied && sudo systemctl restart nodeagent'
  ```

---

## 9. Flatcar OS updates

The OS is **not** a `ClusterVersion` axis. Flatcar's `update_engine` stages an
A/B image from upstream on its own schedule; the nodeagent sets
`REBOOT_STRATEGY=off` so locksmithd never reboots on its own, and takes the
reboot through the same fleet lease as everything else. That is why the OS moved
from 4593.2.4 to 4593.2.5 during the September roll without anyone asking.

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,\
OS:.metadata.annotations.flatcarctl\.anderocloud\.com/running-flatcar,\
OSPENDING:.metadata.annotations.flatcarctl\.anderocloud\.com/os-update-pending'
```

OS reboots sit at the bottom of the priority ladder, so they always defer to a
version roll, and they are ordered only by the single lease — not seed-first.
`status.phase` never reflects one, and `upgrade status` shows only the pending
list. A failed OS reboot does not roll back or halt; it retries.

---

## 10. Out of scope — needs re-provisioning

- A Flatcar **major** or partition-layout change: the image is laid down by
  Tinkerbell `image2disk`, not by a reboot.
- **containerd** content: there is no axis at all; it reaches a cluster only by
  re-imaging.
- A brand-new axis the planner does not know: needs a nodeagent/CRD change
  first.
- **`network` (tenant networks)** is not reachable on this cluster yet — no
  payload on our image, and the first published `network-*.raw` asset lands on
  the next image release. Activation from nothing also requires naming a
  fully-qualified version.

**Pending: the install image itself is stale.** Both Tinkerbell templates still
stream the 2026-07-04 bake (Kubernetes v1.36.2, kube-vip). Re-provisioning a
node today rejoins a v1.37.0 cluster with kube-vip fighting Cilium for the VIP.
Both templates carry a ⚠️ header saying so. Re-baking needs a **Linux host** —
`flatcarctl bake` requires loop devices, `mount` and root, so it cannot run on
this Mac. Pass `--nodeagent-version <the VERSION you built>` or the artifact is
named `nodeagent-dev-x86-64.raw` while the binary inside reports the commit
date, and the axis never matches.

---

## Appendix

**Kubeconfigs** — `~/labb/omni/andero-kubeconfig-lan` (Flatcar, via the seed
`192.168.1.219`; works from off-LAN), `~/labb/omni/andero-kubeconfig` (via the
VIP `192.168.1.150`; does **not** work off-LAN while the mqtt collision
stands), `~/labb/omni/labbet-kubeconfig.yaml` (Talos, hosts the mirror).

**Mirror** — `http://192.168.1.141:7173`, served by the `hookos` pod's nginx
container from `/usr/share/nginx/html` on the `hook-artifacts` PVC (10Gi).
`FLATCARCTL_SYSEXT_BASE_URL` is set both in a systemd drop-in on each live node
and in both Tinkerbell templates.

**Node annotations** (`flatcarctl.anderocloud.com/`) — `running-kubernetes`,
`running-cilium`, `running-kubevirt`, `running-portal`, `running-iam`,
`running-network`, `running-nodeagent`, `running-flatcar`, `node-class`,
`reconcile-phase`, `rebooted-generation`, `os-update-pending`,
`upgrade-failed`, `failed-version`, `credential-expiry`.

**On-node state** (`/var/lib/nodeagent/`) — `portal-applied`, `iam-applied`,
`cilium-applied-version` (all hold a version string), `upgrade-halted`,
`reboot-in-progress`, `sysext-previous-<name>` (rollback records),
`cilium-vip-applied`, `upgrade-api-installed` (fingerprints).
Live version files the agent reads: `/usr/local/share/<axis>-version`.
