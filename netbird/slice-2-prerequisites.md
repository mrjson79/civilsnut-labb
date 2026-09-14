# NetBird Slice 2 prerequisite assessment — 2026-09-14

Status: started; deployment is blocked on external reachability and the image vulnerability gate. Slice 2 is not complete. HA access remains disabled. No live resources changed.

## Observed lab state

- All nine civilsnut-labbet nodes Ready; Kubernetes v1.36.4.
- Live shared Cilium Gateway: 192.168.4.12, Programmed=True; checked-in annotation requests 192.168.4.10. Resolve the intended address before designing new forwarding.
- Public DNS queries to 1.1.1.1 return NXDOMAIN for netbird.civilsnut.se and idp.civilsnut.se.
- No public router/NAT endpoint was established from the repository or notes. Asked the user which endpoint/router can forward TCP 443 and UDP 3478.

## Stable image candidates

Official latest releases checked: [NetBird v0.78.1](https://github.com/netbirdio/netbird/releases/tag/v0.78.1), [dashboard v2.92.0](https://github.com/netbirdio/dashboard/releases/tag/v2.92.0). These are candidates, not an approved or tested deployment version set.

| Image | Immutable index digest | Platforms verified |
|---|---|---|
| netbirdio/netbird-server:0.78.1 | sha256:3086534361a18573b85897383a0753a97b8c75d68dee9926fbd7eccab1f2fe89 | linux/amd64, linux/arm64 |
| netbirdio/dashboard:v2.92.0 | sha256:fa2d8b02a81761e4d2a22df4041d13316b7635f1e93273eafeb53d4991e55b5a | linux/amd64, linux/arm64 |

Both architecture variants were scanned through Slice 1's pinned Trivy 0.73.0 wrapper, remote image source, HIGH/CRITICAL threshold. Images were not executed. Server: 7 HIGH/0 CRITICAL per architecture. Dashboard: 2 HIGH/0 CRITICAL package findings per architecture (one advisory affecting two packages). Reports are local ignored artifacts under tools/netbird/.build/slice2-*.json.

| Candidate | Finding | Package | Installed | Scanner-reported fixed version |
|---|---|---|---|---|
| netbird-server | CVE-2026-41567 | github.com/docker/docker | v28.0.1+incompatible | Not reported |
| netbird-server | CVE-2026-42306 | github.com/docker/docker | v28.0.1+incompatible | Not reported |
| netbird-server | CVE-2026-56864 | golang.org/x/mod | v0.39.0 | 0.40.0 |
| netbird-server | CVE-2026-56865 | golang.org/x/mod | v0.39.0 | 0.40.0 |
| netbird-server | CVE-2026-84304 | google.golang.org/grpc | v1.80.0 | 1.83.1 |
| netbird-server | CVE-2026-84445 | google.golang.org/grpc | v1.80.0 | 1.82.2, 1.83.2, 1.85.0-dev.0.20260825072537-93e31b48545e |
| netbird-server | GHSA-hrxh-6v49-42gf | google.golang.org/grpc | v1.80.0 | 1.82.1 |
| dashboard | CVE-2026-14456 | libcrypto3 | 3.5.7-r0 | 3.5.8-r0 |
| dashboard | CVE-2026-14456 | libssl3 | 3.5.7-r0 | 3.5.8-r0 |

Findings are scanner results, not proof every vulnerable code path is reachable. No suppressions or threshold changes were introduced. The dashboard scan found OS packages but no language-package inventory; it does not establish complete bundled JavaScript dependency coverage.

## Resume conditions and next work

1. Establish the self-hosted public endpoint, router/firewall owner and TCP 443/UDP 3478 path; publish the required control/login DNS records. Validate from a real external network. Do not expose unclaimed administration.
2. Select or produce patched immutable images, retain source/build provenance, and rerun both-architecture scans; reassess actual reachability before any narrowly justified exception. No blanket HIGH-severity waiver.
3. Resolve the Gateway address discrepancy and render the final storage/secrets/routes through the validation path before adding Flux resources.
4. Bootstrap administration privately, verify anonymous denial, then test HTTPS/gRPC/WebSocket/STUN externally.
5. Implement a consistent state backup and prove an isolated restore retains administrator/configuration within 30 minutes. These acceptance checks remain unexecuted.

NetBird combined-server protocol reference: [external reverse proxy](https://docs.netbird.io/selfhosted/external-reverse-proxy). HTTP/gRPC/WebSocket forwarding does not provide the direct UDP STUN path.
