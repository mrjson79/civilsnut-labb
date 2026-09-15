# NetBird Home Assistant access

Slice 1 provides a validation gate for the civilsnut home lab. NetBird is not
installed. `access.json` defaults to disabled, with no routes, DNS records,
source groups or deployment images. This directory is outside Flux's `fluxcd/`
reconciliation path and contains no live resources.

## Run the gate

Prerequisites: Python 3.13 or newer, Make, a running Docker engine, and outbound
access to PyPI, GHCR, Docker Hub and the public Kubernetes schema repository.

```sh
make validate-netbird
```

The same command runs on every PR and every push to main. It creates an isolated
Python environment with pinned dependencies, renders the access contract, runs
policy tests, Ruff formatting/lint, YAML lint, strict Kubernetes schemas, secret
scanning and HIGH/CRITICAL image vulnerability checks. Scanner containers are
pinned by digest and receive only the NetBird directory and a scratch directory;
no cluster credentials or Docker socket are mounted. Nothing is applied.

`make test-netbird` runs the fast contracts only; it is not a substitute for the
full gate. `make format-netbird` formats Python. Generated output and scanner
caches live in `tools/netbird/.build/` and are ignored by Git.

## Contract and boundaries

- Disabled: destination must be null and source groups empty. Rendered allow
  rules, routes and DNS records are empty.
- Enabled fixture: explicit pilot groups, dedicated IPv4 /32, TCP 443 only,
  hostname `ha-vpn.civilsnut.se`, no bidirectional access or broad source groups.
- An IP/port contract alone cannot establish that a gateway serves only HA.
  Dedicated-gateway Host/SNI denial and real access/revocation tests belong to
  the HA integration slice.
- `access-plan.json` is an intermediate contract, not a NetBird API payload or
  an implemented live kill switch. Later slices must translate resource/group
  references and prove revocation of both new and established sessions.
- Put fully rendered Kubernetes YAML/JSON in `manifests/`. Unknown schemas fail;
  HelmRelease/Kustomization inputs are rejected until rendered. Later deployment
  work must wire the same rendered artifacts into validation and Flux; adding
  resources elsewhere does not make them covered by this scoped gate.
- All workload images must be immutable digest references in `access.json`.
  Declared architectures are verified against registry metadata while scanning.
  A single-architecture image needs an explicit compatible node selector for
  this mixed amd64/arm64 cluster. Unused inventory entries are rejected.
- Kubernetes Secret values and inline credential fields are forbidden. Use
  External Secrets/1Password references. Trivy additionally scans recognizable
  secrets. These checks cannot identify every possible opaque credential.

No production image has been selected yet: the gate explicitly reports the
empty inventory. Its integration tests scan a pinned obsolete Alpine image
(without executing it) and assert actual HIGH/CRITICAL findings; an unavailable
registry or scanner error cannot satisfy that test. Other real-tool fixtures
prove schema acceptance/rejection and synthetic-secret detection. Enabled and
disabled access contracts are tested without installing anything.

## Delivery, rollback and maintenance

Current delivery: commit to main → GitHub validation; Flux independently watches
`fluxcd/`. This slice adds no Flux resource. Before adding production manifests,
require the `Validate NetBird / validate` check in repository branch protection
and route changes through reviewed PRs. A CI failure after a direct main push
cannot prevent Flux from consuming that push. Branch protection is repository
administration and is not changed by this slice.

Rollback this slice by reverting its commit. No cluster cleanup, secret rotation
or state removal is needed. For future enabled deployment, changing a flag or
suspending Flux will only revoke access once the later live reconciliation work
exists and has been tested.

Update Python pins, scanner digests and `kubernetesVersion` deliberately, then
run the full gate. Schema downloads and the vulnerability database are current
external data, so results can change as advisories or schemas change. Do not
ignore missing schemas or scan failures. NetBird CRD schemas and the selected
stable server/operator/peer version set must be added and validated in the
slice that introduces those resources.

Full plan: [specification](../docs/specs/001-netbird-home-assistant-access.md).

Outbound-only continuation: [bootstrap candidate and current blockers](bootstrap/README.md).
