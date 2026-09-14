"""Exercise the real scanner binaries, including deliberate rejection fixtures."""

import json
import subprocess

import pytest
import yaml

from test_gate import ROOT, gate


def test_ci_runs_the_complete_gate_on_pr_and_main():
    workflow = yaml.load(
        (ROOT / ".github/workflows/validate-netbird.yaml").read_text(),
        Loader=yaml.BaseLoader,
    )
    events = workflow["on"]
    assert "pull_request" in events
    assert events["push"]["branches"] == ["main"]
    assert "paths" not in events["push"]
    assert not events["pull_request"]
    assert workflow["permissions"] == {"contents": "read"}
    commands = [step.get("run") for step in workflow["jobs"]["validate"]["steps"]]
    assert "make validate-netbird" in commands


@pytest.mark.tools
def test_kubernetes_schema_accepts_valid_and_rejects_invalid_and_unknown():
    gate.BUILD.mkdir(exist_ok=True)
    path = gate.BUILD / "schema-fixture.yaml"
    path.write_text(
        "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: netbird-test\n"
    )
    gate.validate_schemas(path)
    for document in [
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: bad\nspec:\n  replicas: invalid\n",
        "apiVersion: unknown.example/v1\nkind: Unknown\nmetadata:\n  name: bad\n",
    ]:
        path.write_text(document)
        with pytest.raises(subprocess.CalledProcessError):
            gate.validate_schemas(path)


@pytest.mark.tools
def test_secret_scanner_rejects_synthetic_token():
    directory = gate.BUILD / "secret-fixture"
    directory.mkdir(exist_ok=True)
    # Synthetic recognizable token, never a real credential.
    (directory / "config.txt").write_text(
        "token = ghp_" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0iL3oR6" + "\n"
    )
    output = gate.BUILD / "secret-report.json"
    output.unlink(missing_ok=True)
    with pytest.raises(subprocess.CalledProcessError):
        gate.docker_tool(
            "trivy",
            [
                "fs",
                "--scanners",
                "secret",
                "--exit-code",
                "1",
                "--no-progress",
                "--format",
                "json",
                "--output",
                "/output/secret-report.json",
                "/output/secret-fixture",
            ],
            capture=True,
        )
    report = json.loads(output.read_text())
    assert any(result.get("Secrets") for result in report["Results"])


@pytest.mark.tools
def test_image_scanner_rejects_known_vulnerable_image():
    # Alpine 3.10 amd64, deliberately obsolete. Scan only; never execute it.
    output = gate.BUILD / "image-report.json"
    output.unlink(missing_ok=True)
    with pytest.raises(subprocess.CalledProcessError):
        gate.scan_images(
            {
                "images": [
                    {
                        "image": "docker.io/library/alpine@sha256:e515aad2ed234a5072c4d2ef86a1cb77d5bfe4b11aa865d9214875734c4eeb3c",
                        "platforms": ["amd64"],
                    }
                ]
            }
        )
    report = json.loads(output.read_text())
    # A download/tool error must not be mistaken for a successful rejection test.
    assert any(
        item["Severity"] in {"HIGH", "CRITICAL"}
        for result in report["Results"]
        for item in result.get("Vulnerabilities", [])
    )
    assert report["Metadata"]["ImageConfig"]["architecture"] == "amd64"
    assert report["Metadata"]["ImageConfig"]["os"] == "linux"
