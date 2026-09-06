# Gateway API upgrades

## Target and compatibility

As checked on 2026-09-06, the latest stable release is
[v1.6.2](https://github.com/kubernetes-sigs/gateway-api/releases/tag/v1.6.2)
(released 2026-09-03). The repository upgrade is from v1.6.0 to v1.6.2.
The experimental bundle is still required for the HTTPRoute ExternalAuth
filter; a stable release tag does not make its experimental fields GA.

[Cilium 1.20.1 documents Gateway API v1.6.1 support](https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/).
Comparison of the rendered v1.6.2 bundle with our existing v1.6.0 bundle
found the same 13 CRDs. The only spec changes are HTTPRoute description text
clarifying redirect status-code conformance; validation rules and served/storage
versions are unchanged. This supports using the patch release without changing
Cilium or the routes, subject to the rollout checks below.

## Update mechanism

`fluxcd/00-foundation/gateway-api/kustomization.yaml` references an exact GitHub
release asset. Kustomize deletion patches exclude only the existing
`safe-upgrades.gateway.networking.k8s.io` ValidatingAdmissionPolicy and binding.
This preserves the previous vendored bundle's exclusions without maintaining
a generated CRD file in Git.

Flux now needs access to GitHub release assets when rendering this resource.
The live kustomize-controller does not disable remote bases. A failed download
prevents reconciliation; it does not itself remove the installed CRDs.

Renovate's custom regex manager updates the release URL. The README manager
updates both version tables in the same Gateway API group. Only stable numeric
release tags are allowed; monthly releases and prereleases are excluded.
All Gateway API updates require manual merge, including patches, and retain
the repository's three-day minimum release age. Future minor/major releases
must be checked against Cilium support and ExternalAuth before merging.

## Rollout plan

1. Review and merge the prepared repository change after the checks below.
   No live upgrade was performed during preparation.
2. Let the `flux-system` Kustomization reconcile the merged main branch.
3. Verify all 13 CRDs report bundle version v1.6.2, `flux-system` is Ready,
   and `gateway-system/shared-gateway` remains Programmed.
4. Verify HTTPRoute parent conditions are Accepted and ResolvedRefs. Exercise
   the Hubble and Zigbee2MQTT ExternalAuth login flows and an ordinary route
   such as Home Assistant. Inspect Cilium operator logs if routes regress.
5. If this patch causes a regression, revert the repository change and let
   Flux reconcile. For this specific upgrade the CRD validation/storage
   schemas are unchanged. Do not assume future minor/major CRD downgrades
   are safe; inspect stored versions and schema changes first.

## Pre-merge checks

Run from the repository root:

```sh
kubectl kustomize fluxcd/00-foundation/gateway-api > /tmp/gateway-api.yaml
kubectl --kubeconfig labbet-kubeconfig.yaml apply --server-side --dry-run=server --field-manager=kustomize-controller -f /tmp/gateway-api.yaml
npx --yes --package renovate renovate-config-validator renovate.json
```

Also compare the rendered CRDs with the previous release: confirm the same
resource identities, retain ExternalAuth, exclude the two policy resources,
and review all schema changes. The v1.6.2 rendering and server-side dry run
passed for all 13 CRDs. Renovate regex checks matched the release URL and both
README entries, accepted stable patch/minor/major tags, and rejected monthly
and prerelease tags.

The official Renovate validator passed. Its local installation fell back to
JavaScript RegExp because native RE2 was unavailable; the added expressions use
no lookarounds or backreferences.
