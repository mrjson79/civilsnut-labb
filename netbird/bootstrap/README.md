# Outbound-only bootstrap candidate

Status (2026-09-15): prepared and rendered, not deployed. NetBird Cloud is the
working hosting choice after the request to continue without inbound home-router
ports. The user supplied the Cloud credential and the empty tenant is now bootstrapped; no peers are enrolled. Home Assistant access stays off.
The self-hosted server/dashboard and public lab DNS prerequisites no longer apply
to this proposed Cloud path. Cloud login must work independently of private Zitadel.

## Prepared configuration

`operator-values.yaml` pins operator v0.8.0 and peer 0.78.1 by immutable digest.
`externalsecret.yaml` references the existing `onepassword-connect` store and
item `netbird-civilsnut-labbet`, field `api-token`, in the civilsnut.se vault.
The user created this item and its token was verified against api.netbird.io.
It belongs to an unblocked owner account (not a service user). The token was
read only into memory and never printed or saved in repository files. Use a
dedicated service identity before leaving a persistent operator deployment.

```sh
make render-netbird-bootstrap
```

The command fetches chart 0.8.0 by immutable OCI digest and writes
`tools/netbird/.build/bootstrap-candidate.yaml`. It does not apply anything.
The chart's `allowAllSecrets: false` value does not remove its cluster-wide
Secret rule in the rendered output. `tools/netbird/bootstrap.py` therefore moves
that rule into a Role bound only in namespace `netbird`, preserving other rules.
Unexpected wildcard/subresource grants fail rendering. Regression tests cover
the split and rejection cases. Runtime compatibility with this narrower Role
still needs verification; the operator may require changes if it watches Secrets
across namespaces. Namespace-scoped webhooks do not scope its other controllers.

Actual output inspection: 13 resources, no cluster Secret grants, no public
Service types, no host networking, no NetworkRouter/NetworkResource/HA routes.
This is not a complete install bundle: Helm CRDs, the Namespace, ExternalSecret
and final Flux wiring must be included and schema-validated before deployment.
Do not apply the raw upstream chart: that bypasses the RBAC transformation.

## Image gate results

Trivy 0.73.0 with its updated 2026-09-15 database scanned both linux/amd64 and
linux/arm64 variants by digest:

| Candidate | HIGH per architecture | CRITICAL |
|---|---:|---:|
| Operator v0.8.0 | 9 | 0 |
| Peer 0.78.1 | 5 | 0 |

Reports: ignored local files `tools/netbird/.build/outbound-{operator,peer}-{amd64,arm64}.json`.
No image was executed, no findings suppressed, and no threshold relaxed. These
candidates fail the deployment image gate. Passing the repository's disabled
configuration tests does not approve these separate draft images for deployment.
Review patched upstream builds or a reproducible patched build before proceeding.

## Cloud replacement for Slice 2

Before enrollment, obtain the tenant API credential through 1Password, verify
its tenant identity, and inspect policies for existing broad/default access.
Use a dedicated pilot group; do not modify unrelated tenant policies implicitly.
Prepare a recoverable export of policy/group/DNS configuration and test recreating
only isolated pilot objects. Managed server/database backup is the provider's
responsibility; local server restore is not an applicable acceptance criterion.

Then deploy validated operator resources, verify readiness with scoped RBAC,
and enroll a dedicated routing peer with no HA resource or allow policy. Test
outbound Cloud connectivity and reconnection from an external client before the
later HA-only /32 TCP 443 and real revocation slices. Do not claim enrollment,
recovery, external connectivity or access denial based on rendering alone.

Sources: [Kubernetes operator](https://docs.netbird.io/use-cases/kubernetes),
[routing peers](https://docs.netbird.io/use-cases/kubernetes/routing-peer),
[outbound connectivity](https://docs.netbird.io/manage/networks/sizing-routing-peers).


## Verified Cloud bootstrap — 2026-09-15

- Token authenticated successfully; current role owner, not blocked.
- Initial tenant had zero peers/networks and only the enabled Default All-to-All policy.
- Disabled both the Default policy and its rule, then verified the returned state.
- Created empty groups `civilsnut-ha-pilot` and `civilsnut-ha-routing-peers`.
- Exported a temporary empty group, deleted/recreated it, checked its name and
  empty memberships, and removed it again (1.7 seconds). This tests only an empty
  group, not policy/DNS/reference recovery or peer state.
- Verified final state: zero peers, zero networks, no enabled policies. No HA
  endpoint, client, public DNS, home-router rule or cluster resource changed.
- The original policy/group snapshot is stored locally with mode 0600 at
  `tools/netbird/.build/cloud-bootstrap-before.json`; it contains no API token.

The credential prerequisite is resolved. Image remediation remains: newest peer
0.78.2 (index sha256:0d6653f21f0417b6014e4c621c75e898e06698e1cce973398d1c3c45a30f6bd6)
was scanned on both architectures and still has 5 HIGH findings each: two OpenSSL
package findings plus three gRPC advisories. Scanner-reported fixes are OpenSSL
3.5.8-r0 and gRPC 1.83.2. Operator 0.8.0 is still latest; its recorded fixes are a
Go toolchain at least 1.26.6 and golang.org/x/text 0.39.0. These are remediation
candidates, not proof a patched build is compatible or clean. A rebuild needs
pinned sources/toolchains, dependency tests, both-architecture scans, registry
provenance, and the scoped-RBAC runtime test before deployment. No bypass added.
