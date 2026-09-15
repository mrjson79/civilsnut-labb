# Lab patch builds

These builds address the image gate findings without suppressing advisories.
Upstream source commits and archive checksums are in `sources.json`; builder and
runtime base images are pinned by digest. Sources are extracted only under the
ignored build directory. Dependency changes happen inside the builder.

- Operator 0.8.0: Go 1.26.7 and golang.org/x/text 0.39.0; upstream k8sutil/package tests.
- Peer 0.78.2: gRPC 1.83.2 and OpenSSL 3.5.8-r0; upstream management/signal client tests.
  Test servers require CGO for SQLite, while the shipped peer binary uses CGO=0.
- Tests run in the builder's native architecture. Binary target architecture is
  explicit. The publication workflow uses native amd64 and arm64 runners.

`tools/netbird/build_patched_images.py COMPONENT ARCHITECTURE` fetches and verifies
source, builds, tests, and scans the actual image archive for HIGH/CRITICAL
findings. `--push` publishes only after successful tests, scan and architecture
verification. It requires an existing registry login; it never reads NetBird or
1Password credentials. Python dependencies come from `make test-netbird`.

The manually dispatched Publish patched NetBird workflow uses the repository's
short-lived GitHub token to publish per-architecture images to GHCR. Deployment
must pin the published digests and verify pull access from the cluster. Merely
publishing an image does not change Flux or grant VPN access.

Builds use pinned primary inputs and Go module checksums, but APK repository
availability and transitive package versions can change. Retain successful scan
reports and image digests; do not claim bit-for-bit reproducibility from these
Dockerfiles alone. Any future patch release must pass the same tests and scans.

Local ARM64 checks: both images had zero HIGH/CRITICAL findings. Operator tests
passed. Peer management/signal tests passed after enabling CGO for their test
server. AMD64 validation and registry publication are still in progress.
