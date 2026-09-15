# Spec 001: NetBird VPN access to Home Assistant

**Date:** 2026-09-14
**Status:** Slice 1 implemented; remaining slices planned
**Owner:** Anders Johansson — civilsnut home lab
**Feature flag:** `netbird-home-assistant-access` (default: off)

## Hosting revision — 2026-09-15

User requested continuation after clarifying that inbound home-router ports are
not required. Working choice: NetBird Cloud, with outbound-only lab routing peers.
The original self-hosted Slice 2 below is retained as an alternative, not the
active deployment plan. Cloud Slice 2 covers tenant identity/policy bootstrap,
1Password-backed API credentials, scoped operator setup, outbound connectivity
and recoverable pilot configuration. Managed-server restore is replaced by
pilot configuration recovery; private Zitadel is not a bootstrap dependency.
See [bootstrap candidate](../../netbird/bootstrap/README.md) for exact status.
No tenant/enrollment or recovery test is complete. Operator/peer candidate image
scans fail the existing gate; no Cloud credential is available yet.

## Foundations assessment

**Project context:** Brownfield
**Build abstraction:** Slice 1 adds `make validate-netbird`; `make smoke-netbird` remains for live integration slices. Unrelated nested application builds are outside this assessment.
**CI pipeline:** GitHub Actions for Renovate and Slice 1 NetBird validation on PRs/every main push. Existing non-NetBird deployments remain outside this scoped gate.
**Test framework:** No automated NetBird/manifest regression suite or passing test was found for this deployment path — proposed: pytest integration/contract tests over rendered manifests and an isolated Kubernetes fixture.
**Deploy path:** GitHub main → Flux source/Kustomization → Kubernetes manifests and HelmReleases → controller reconciliation. Production target is only `civilsnut-labbet`.
**Feature flags:** No established NetBird gate — proposed: declarative access-policy enablement, initially disabled, with an empty pilot-device group. Infrastructure can run while HA access remains off.
**Trunk discipline:** Main is the deployment branch. Recent history shows same-day merges and direct operational fixes. Individual branch lifetimes were not measured.
**Quality gates:** Renovate dependency discovery exists. Blocking formatting, YAML/schema validation, access-policy tests, secret scanning, and image vulnerability checks are missing for this change path; add them in Slice 1. Application type-checking is N/A for upstream images; Kubernetes schemas and policy contracts are the type boundary.
**Biggest constraint (brownfield only):** Main is deployed automatically without an automated check that the resulting service is usable and its access policy is correctly restricted.
**Foundation slices required before / alongside feature work:** 1. Focused validation and disabled-access gate before NetBird deployment. 2. External connectivity and state-recovery checks alongside the control-plane slice. 3. Upgrade/rollback and monitoring checks before declaring the pilot complete.

Value stream: edit manifests → manual review/render/dry-run → commit/merge main → Flux fetch → reconcile resources/Helm → inspect readiness → manually exercise service. The constraint is the manual validation step, not the absence of deployment automation. Keep existing applications delivering; do not retrofit the entire repository.

Observed service: `home-assistant/home-assistant:8123`, exposed as `ha.civilsnut.se` through Cilium's shared Gateway. Home Assistant runs with host networking. Existing monitoring, Zitadel, cert-manager, External Secrets/1Password and Rook-Ceph can be reused. Recent checks found healthy nodes and Ceph, but this is not a NetBird compatibility test.

## Goal

Let Anders securely reach Home Assistant from a laptop and phone outside the home network using NetBird VPN, including the HA browser UI and companion app. Provide access to the HA endpoint only, retain Home Assistant authentication, and preserve existing local access. Manage deployment through the existing home-lab GitOps path and record operational decisions in Secondbrain.

## Acceptance criteria

- [ ] An explicitly enrolled pilot laptop connects from an external network and loads the HA login page over valid HTTPS.
- [ ] After normal HA authentication, dashboard data and WebSocket updates work; unauthenticated API requests remain denied.
- [ ] A pilot phone uses the HA companion app over cellular with Wi-Fi disabled and reconnects after network changes.
- [ ] The NetBird policy permits only the dedicated HA resource on TCP 443; unrelated LAN services, Kubernetes/Talos APIs, other shared-gateway applications and the default internet route are not granted.
- [ ] An unapproved or revoked peer cannot establish HA connections; revocation terminates the tested existing session within the agreed bound.
- [ ] Turning the access flag off removes VPN reachability and its private DNS publication without interrupting local HA access or deleting state.
- [ ] Routing-peer restart and a forced relay connection recover within the defined pilot bounds; control-plane state can be restored without recreating policies or identities.
- [ ] CI validates changes, Flux health is observable, stable-version update PRs require review, and the rollback/recovery procedure and Secondbrain notes are current.

## Out of scope

- Full-tunnel internet VPN, exit-node service, whole-LAN routing and access to other clusters.
- Replacing or removing any existing VPN, public ingress, local HA URL, or client network profile.
- Public sharing of HA through NetBird's Reverse Proxy product.
- Replacing HA authentication with Zitadel or adding an interactive OAuth proxy in front of HA API/WebSocket traffic.
- Family-wide rollout, simultaneous support for both mobile platforms, multi-site networking, or a highly available control plane in the first pilot.
- New HA functionality, discovery/mDNS forwarding, or changes to IoT device connectivity.

## Constraints and assumptions

- **Confirmed:** NetBird is for VPN and Home Assistant access in the civilsnut home lab; Slice 1 implementation was authorized on 2026-09-14; later slices remain planned.
- **Hosting assumption:** self-host the NetBird control plane in civilsnut-labbet; use existing Zitadel through the supported NetBird identity-provider connector. The user has not yet selected self-hosted versus Cloud. If Cloud is chosen, replace Slice 2 with tenant bootstrap and omit self-hosted ingress/storage; retain the access tests and HA design.
- **Users/devices assumption:** Anders only, one macOS laptop and one phone. Pick the actual phone OS before Slice 5; do not assume an iOS or Android-specific always-on behavior.
- **VPN scope assumption:** split tunnel to HA only. Broad home-network access requires a separate scope decision.
- **Endpoint proposal:** `ha-vpn.civilsnut.se` on a dedicated internal Cilium Gateway address. Reuse the wildcard certificate only after validating its reference permissions. Keep `ha.civilsnut.se` unchanged during the pilot.
- **Control endpoint proposal:** `netbird.civilsnut.se`. Confirm DNS, NAT/public-IP availability, firewall ownership and certificate issuance before Slice 2. Existing private Gateway addresses alone do not prove internet reachability.
- **Bootstrap constraint:** a fresh external client must reach NetBird and the required Zitadel login endpoints before joining the VPN. If CGNAT or firewall restrictions prevent this, stop that slice and revise hosting to a reachable endpoint or Cloud; do not silently expose unrelated services.
- **Compatibility:** select and pin stable upstream server, dashboard, operator and peer versions when implementing. Validate the complete version set, client support, image architectures and Talos/Cilium datapath. Do not copy `latest` tags from examples.
- **Pilot recovery objectives (proposed, negotiable):** 60 seconds for a healthy client to reconnect after peer/network transition; 60 seconds for online peer revocation to block both a fresh request and the tested existing WebSocket; 30-minute control-plane restore objective. These are acceptance targets, not claims about upstream guarantees.
- **Storage:** one control-plane replica with a supported persistent backend on Ceph for the pilot. Use consistent backups and verify restore before relying on it. Retain PVs and identity secrets on rollback. No claim of access during a home-cluster outage.
- **Secrets:** use External Secrets and 1Password; no setup keys, API tokens, passwords or HA tokens in Git or test output. Verify required operator permissions with a dedicated service identity.
- **Test safety:** an isolated network and synthetic HA endpoint cover negative tests in CI. Production smoke tests are read-only; no automations, locks, alarms or physical devices are actuated. Test notifications, if needed later, require explicit authorization.
- **Repository detail:** `docs/` is locally ignored. This spec is saved at the skill-required location, but a later explicit commit must force-add this document or deliberately adjust tracking. The initial planning task changed no deployment configuration; Slice 1 adds validation only.

### Proposed architecture and access boundaries

Control path: external NetBird client → publicly reachable HTTPS control endpoint → NetBird server and dashboard; login redirects to existing Zitadel. Use the current combined server model, with Zitadel connected through its supported embedded-IdP integration, rather than deploying a second Zitadel instance. [NetBird identity-provider guidance](https://docs.netbird.io/selfhosted/identity-providers/zitadel)

Data path: enrolled client → encrypted direct or relayed NetBird connection → Kubernetes routing peer → dedicated HA Gateway TCP 443 → HA Service TCP 8123. Prefer the official Kubernetes operator's routing resources; validate it against the selected server before enabling access. Keep credentials/state stable through pod replacement. [NetBird Kubernetes routing](https://docs.netbird.io/use-cases/kubernetes/routing-peer)

A shared Gateway address is not an HA-only boundary: other hostnames can use the same IP and port. Allocate a dedicated internal Gateway/Service that accepts only the HA VPN hostname, restrict route attachment, and publish only that destination. Test alternate Host/SNI values against it. Do not publish node, pod, service or LAN subnet routes. The routing peer does not run directly on Talos or inside the existing host-network HA pod.

Use a narrow NetBird custom DNS zone/record for the VPN endpoint, distributed only to the pilot group. Validate the chosen zone/record form, including apex support if used. Do not override the entire `civilsnut.se` zone or public DNS resolution. Private DNS visibility is convenience, not authorization; the access policy enforces denial. [Custom DNS zones](https://docs.netbird.io/manage/dns/custom-zones)

For a combined self-hosted server, the external proxy must support HTTP, h2c-backed gRPC and WebSocket endpoints; STUN needs separate UDP 3478 reachability. Translate the documented endpoint map into Cilium Gateway API routes and verify with a real client. An ordinary dashboard HTTP check is insufficient. Native NetBird Reverse Proxy is outside this design. [External proxy requirements](https://docs.netbird.io/selfhosted/external-reverse-proxy)

Flag semantics: `netbird-home-assistant-access=false` means the HA allow policy is disabled and its pilot DNS record is withdrawn. Infrastructure and persistent state remain. Reconciliation suspension alone is not a security flag: it leaves existing policies active. The flag transition must be idempotent and tested against both new and established connections. Document initial dashboard/API bootstrap steps before automating their most error-prone policy operations.

## Vertical slices

Each slice is independently deployable in ≤ 2 days, behind the feature flag.

Slice ordering rules:
- **Greenfield/Greenfield-late:** Slice 1 is **Feature Zero** (pipeline + build + first test + Hello World to production + rollback + flag mechanism). No feature slice precedes it.
- **Brownfield:** the first foundation slice addresses the single biggest constraint identified above. Feature slices may interleave with subsequent foundation slices, but no slice claims "deployable" without a path to production.

Estimates cover implementation, tests, documentation and integration for one engineer once external prerequisites are available. Each numbered RED/GREEN step is a few hours at most. External DNS/provider waiting time is a prerequisite, not hidden inside a two-day estimate. If an integration fails and exceeds the estimate, stop and re-slice the new finding before expanding scope. Later slices depend on stable interfaces from earlier ones; none requires an unmerged branch. Operator/deployment details remain negotiable while acceptance boundaries stay fixed.

### Slice 1: Reject unsafe NetBird changes before they reach the lab

- **Implementation status:** Implemented: `make validate-netbird` passes 27 contract/tool tests plus lint, formatting and source scans. Trunk CI verification follows integration. No live resources or access enabled.
- **Value:** Main remains deployable while incomplete VPN work lands with no HA access.
- **Acceptance:**
  - [x] One command validates enabled/disabled rendering, schemas, policy contracts, formatting, secrets and selected image vulnerabilities; CI runs it on PRs and every main push.
  - [x] A deliberately broad route, plaintext credential, missing architecture selection for an incompatible image, or HA allow-policy in the off configuration fails the gate.
  - [x] The valid disabled fixture passes and adds no live NetBird access; existing application manifests remain unchanged.
- **Estimate:** 1.5 days.
- **Flag behaviour:** Validation always runs; feature defaults off. Test both desired-policy states in fixtures.
- **Dependencies:** none.

#### TDD plan

1. 🔴 RED — `test_netbird_off_grants_no_access` (contract): enabled HA allow-policy in a disabled fixture is not rejected because validation is absent.
2. 🟢 GREEN — add the smallest fixture validator and `make validate-netbird` in `Makefile` and `tests/netbird/`; reject that unsafe state.
3. 🔴 RED — `test_netbird_change_gate_rejects_invalid_inputs` (integration): broad CIDRs, invalid CRDs, a seeded fake secret and incompatible image platform are accepted.
4. 🟢 GREEN — connect pinned schema/lint/secret/image checks and policy assertions; include one valid passing fixture and deployable disabled rendering.
5. 🔴 RED — `test_ci_executes_netbird_gate_on_pr_and_main` (contract): no GitHub Actions validation job exists.
6. 🟢 GREEN — add `.github/workflows/validate-netbird.yaml` using the same command; document the current deploy/rollback path and test-runner requirements.
7. Integrate to trunk behind flag `netbird-home-assistant-access` (state: off). CI is active immediately; no production resources are enabled.

### Slice 2: Reach and recover a private NetBird administration service

- **Implementation status (2026-09-14):** Prerequisite assessment started; public control/login DNS is NXDOMAIN and stable candidate images fail the HIGH-severity gate. No deployment or recovery acceptance claimed. See [assessment](../../netbird/slice-2-prerequisites.md).

- **Value:** The operator can bootstrap and restore a working VPN control plane without granting HA access.
- **Acceptance:**
  - [ ] A freshly started client from outside the LAN reaches the required control protocols and STUN; TLS and dashboard routes work.
  - [ ] Initial administrator bootstrap occurs before unrestricted internet exposure; anonymous administration is denied.
  - [ ] A consistent state backup restores the bootstrap account and configuration into an isolated instance within 30 minutes.
- **Estimate:** 2 days; DNS/NAT reachability and a usable stable image set must be established before starting.
- **Flag behaviour:** HA access stays off; admin bootstrap has a separately scoped temporary restriction. Retain state on teardown.
- **Dependencies:** Slice 1; agreed hosting and verified external reachability.

#### TDD plan

1. 🔴 RED — `test_external_control_protocols` (integration): isolated deployment lacks reachable HTTPS/gRPC/WebSocket/STUN endpoints.
2. 🟢 GREEN — add pinned server/dashboard manifests, storage, secrets and Cilium routes under the proposed `fluxcd/01-infrastructure/netbird/`; translate the supported upstream configuration without replacing the shared Gateway.
3. 🔴 RED — `test_bootstrap_is_restricted` (e2e): an unauthenticated external client can claim administration or reach protected APIs.
4. 🟢 GREEN — add the supported bootstrap restriction and idempotent bootstrap procedure, then verify authorized admin login and anonymous denial before public enablement.
5. 🔴 RED — `test_restore_retains_control_state` (integration): a clean instance cannot recover the test tenant/configuration from backup.
6. 🟢 GREEN — implement/document a consistent backup and isolated restore with secrets preserved; retain storage on rollback. Validate external reachability with a fresh real client.
7. Integrate to trunk behind flag `netbird-home-assistant-access` (state: off).

### Slice 3: Enroll and revoke a laptop using the existing identity service

- **Value:** Anders can join a controlled VPN with Zitadel without receiving implicit home-network access.
- **Acceptance:**
  - [ ] The pilot laptop authenticates through existing Zitadel; incorrect issuer/audience and unassigned users fail closed.
  - [ ] A new peer receives no HA or LAN access until explicitly assigned; remove any bootstrap allow-all policy.
  - [ ] Revoking the test peer denies reconnection within 60 seconds while the control plane is healthy.
- **Estimate:** 1.5 days.
- **Flag behaviour:** HA access remains off; only a designated pilot user may enroll.
- **Dependencies:** Slice 2; existing Zitadel OIDC administration.

#### TDD plan

1. 🔴 RED — `test_pilot_oidc_enrollment` (e2e): the laptop cannot finish Zitadel login, while negative issuer/user cases have no verified rejection.
2. 🟢 GREEN — configure the supported Zitadel connector, exact redirects and credentials; run positive and negative login cases using a test account.
3. 🔴 RED — `test_new_peer_has_no_home_routes` (integration): default tenant policy or group assignment grants unapproved connectivity.
4. 🟢 GREEN — establish explicit enrollment/pilot groups and default-deny policy; export non-secret desired settings for review.
5. 🔴 RED — `test_peer_revocation_blocks_reconnect` (e2e): removed test peer can reconnect.
6. 🟢 GREEN — implement the smallest idempotent revoke procedure/API operation and verify credential/peer removal behavior; keep human-client credentials out of Git.
7. Integrate to trunk behind flag `netbird-home-assistant-access` (state: off).

### Slice 4: Open only Home Assistant over private HTTPS from the laptop

- **Value:** The first user gets working, restricted remote HA access through the complete path.
- **Acceptance:**
  - [ ] Enabling the pilot flag publishes the dedicated resource and private hostname; HTTPS login, authenticated read and a WebSocket exchange succeed externally.
  - [ ] Unapproved peers, unrelated destination IPs/ports and alternate Host/SNI attempts cannot reach HA or other Gateway apps through this VPN grant.
  - [ ] Disabling the flag or revoking the peer blocks new and tested existing sessions within 60 seconds; local HA access and saved state remain intact.
- **Estimate:** 2 days.
- **Flag behaviour:** Default off; enable only for the pilot laptop after negative tests pass. Off revokes access and private DNS publication, rather than suspending reconciliation.
- **Dependencies:** Slice 3; address reservation and certificate reference validated.

#### TDD plan

1. 🔴 RED — `test_laptop_reaches_only_ha_https` (integration/e2e): the isolated HA fixture has no private TLS/DNS/resource path.
2. 🟢 GREEN — add the official operator/router integration, dedicated HA Gateway and HTTPRoute, scoped custom DNS record and TCP 443 policy. Forward to the existing HA Service. Keep HA login enabled.
3. 🔴 RED — `test_vpn_does_not_grant_other_services` (e2e): an unapproved client, another gateway hostname, LAN endpoint or non-443 port succeeds in the deliberately unsafe fixture.
4. 🟢 GREEN — narrow NetBird resources/policies and Gateway attachment/host rules; avoid whole-subnet advertisements and validate actual routing-peer egress behavior on Talos/Cilium. Grant only capabilities required by the selected peer mode.
5. 🔴 RED — `test_flag_off_revokes_existing_ha_session` (e2e): an existing WebSocket or new connection survives the proposed 60-second bound.
6. 🟢 GREEN — implement and verify real data-plane revocation, including session cleanup if the selected policy mechanism needs it. Withdraw the DNS record; prove local URL and HA data are unchanged.
7. 🔴 RED — `test_real_ha_websocket_requires_auth` (e2e): fixture success does not yet establish real HA login/WebSocket behavior.
8. 🟢 GREEN — exercise read-only HA login/API/WebSocket checks on the real pilot path and adjust proxy handling only where necessary; do not widen HA trusted proxies indiscriminately.
9. Integrate to trunk behind flag `netbird-home-assistant-access` (state: off by default; separately approved pilot-device enablement).

### Slice 5: Use the Home Assistant companion app on cellular and restrictive networks

- **Value:** Remote access works on the device the user carries and when direct peer traffic is unavailable.
- **Acceptance:**
  - [ ] On the selected phone OS, HA companion-app login and live updates work on cellular with Wi-Fi off.
  - [ ] Wi-Fi/cellular transition or sleep/wake reconnects within 60 seconds under healthy conditions; VPN disconnection is shown rather than bypassed through an unintended public fallback.
  - [ ] Blocking direct peer UDP in the test environment forces relay use and still permits the scoped HA request; restoring the network recovers normally.
- **Estimate:** 1 day for one phone OS.
- **Flag behaviour:** Add only the pilot phone to the existing grant; removing it disables its access without changing the laptop.
- **Dependencies:** Slice 4; user-selected phone OS and an external test connection.

#### TDD plan

1. 🔴 RED — `test_mobile_external_ha_session` (e2e): the phone cannot use the private HA URL or maintain its authenticated session.
2. 🟢 GREEN — document/configure the supported client and companion-app URL/DNS settings for the selected OS; retain HA authentication and existing local configuration.
3. 🔴 RED — `test_ha_survives_relay_and_network_transition` (integration/e2e): a forced relay path or network transition breaks access beyond the target.
4. 🟢 GREEN — correct the specific relay/WebSocket/DNS behavior revealed by the test. Automate the relay test; record physical-phone verification separately because a CI container cannot prove mobile OS behavior.
5. Integrate to trunk behind flag `netbird-home-assistant-access` (default: off; pilot phone enabled only after its acceptance checks).

### Slice 6: Detect and recover VPN failures without disrupting local HA

- **Value:** The pilot can be operated and updated without silent loss of remote access.
- **Acceptance:**
  - [ ] Restarting the routing peer preserves enrollment and restores pilot access within 60 seconds; a control-plane outage is observable and never opens access.
  - [ ] A synthetic read-only HA probe through a real test VPN peer detects broken DNS, TLS, routing or WebSocket setup; internal readiness checks remain separately visible.
  - [ ] Stable pinned dependency changes create reviewed Renovate updates, pass the focused CI suite, and have a demonstrated config rollback; schema-changing state rollback requires a compatible backup.
- **Estimate:** 2 days.
- **Flag behaviour:** Keep pilot-only access. Operational checks do not grant extra routes. Off revocation is verified with a healthy control plane; for control-plane failure, document a separate local data-plane stop that preserves state.
- **Dependencies:** Slice 4; Slice 5 evidence required before declaring phone delivery complete.

#### TDD plan

1. 🔴 RED — `test_router_restart_keeps_identity_and_scope` (integration): pod replacement loses enrollment or creates an over-permissive replacement peer.
2. 🟢 GREEN — persist/reconcile peer identity as supported by the operator, constrain scheduling/resources, and verify the same restrictive access after replacement.
3. 🔴 RED — `test_external_probe_detects_broken_vpn_path` (integration): healthy internal pods conceal a failed external HA request.
4. 🟢 GREEN — add a read-only synthetic probe and monitoring rules with a bounded failure interval; provision a controlled external probe runner as part of this step. Validate alert routing configuration without sending unsolicited test messages.
5. 🔴 RED — `test_netbird_upgrade_and_rollback_preserve_policy` (integration/contract): a candidate image/config update lacks stable version tracking or cannot restore the previous policy/state fixture.
6. 🟢 GREEN — add focused Renovate grouping/manual merge rules, an isolated upgrade/rollback test, and a state-compatible recovery procedure. Never treat an image downgrade as a database rollback.
7. 🔵 REFACTOR — consolidate repeated probe/restore commands behind the single-command interface; retain diagnostic logs without credentials.
8. Integrate to trunk behind flag `netbird-home-assistant-access` (default: off). Update repository procedures and Secondbrain with measured results.

## Definition of Done (per slice)

- [ ] Integrated to trunk
- [ ] All tests pass in CI
- [ ] Deployable behind feature flag
- [ ] Documentation updated where user-visible
- [ ] No follow-up tickets created for deferred edge cases within the slice's scope
- [ ] Slice completed in ≤ 2 days after prerequisites, or re-sliced before expanding scope
- [ ] Live behavior validated only in civilsnut-labbet; external-network evidence recorded where applicable
- [ ] Negative access tests, rollback/state-retention checks and relevant Secondbrain notes updated
- [ ] Manual hardware checks distinguished from automated CI tests; no false claim that pod readiness proves VPN or HA access

## Risks

- Shared HA/Grafana gateway destination permits other hostnames — use a dedicated HA-only endpoint and test alternate Host/SNI access.
- Self-hosted login/control services depend on the very lab being accessed — verify public bootstrap reachability and retain the existing local/admin recovery path; this VPN is not out-of-band recovery.
- CGNAT or blocked UDP prevents the chosen hosting model — verify before Slice 2 and revise hosting explicitly if needed.
- Routing-peer privileges and firewall behavior differ across Talos, Cilium and image architectures — inspect supported deployment requirements, test the real datapath, and do not apply an untested generic privileged DaemonSet.
- HA host networking and broadly configured trusted proxies can confuse source identity — preserve application authentication, limit the new proxy route and test forwarded headers; do not make VPN membership a login bypass.
- NetBird overlay/private ranges overlap with existing VPNs or visited LANs — inventory client routes and choose non-conflicting address space before enrollment; do not install a default route.
- In-cluster backups fail with Ceph — test a consistent restore and use an independently stored encrypted backup before depending on remote administration.
- Client revocation/flag-off behavior may not immediately terminate existing sessions — test an active WebSocket explicitly; revise the mechanism before accepting the slice.
- Mobile VPN and DNS behavior is OS-dependent — implement one selected phone platform first and test on cellular.
- A disabled feature gate is mistaken for suspended Flux reconciliation — enforce policy revocation and retain state; suspension is not the off switch.
- New chart/image releases contain incompatible components — pin a verified version set, review Renovate PRs and run an isolated connection/rollback test.

## Change log

- 2026-09-14 — initial draft after repository foundations assessment and user scope clarification: NetBird VPN for Home Assistant. Self-hosted/Zitadel remains an explicit hosting assumption pending user preference. No cluster changes, credentials, clients or deployments created.
