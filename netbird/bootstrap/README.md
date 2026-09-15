# Outbound-only bootstrap candidate

Status (2026-09-15): prepared and rendered, not deployed. NetBird Cloud is the
working hosting choice after the request to continue without inbound home-router
ports; no tenant has been created or enrolled. Home Assistant access stays off.
The self-hosted server/dashboard and public lab DNS prerequisites no longer apply
to this proposed Cloud path. Cloud login must work independently of private Zitadel.

## Prepared configuration

`operator-values.yaml` pins operator v0.8.0 and peer 0.78.1 by immutable digest.
`externalsecret.yaml` references the existing `onepassword-connect` store and
item `netbird-civilsnut-labbet`, field `api-token`, in the civilsnut.se vault.
A title-only lookup found no existing NetBird item. No credential was read or
created. This environment has no available browser session for Cloud sign-in.

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
