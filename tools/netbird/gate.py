"""Fail-closed, read-only preflight for the scoped NetBird delivery path.

The access plan is an intermediate contract, NOT an API call or a live off switch.
A later slice must translate group/resource references and enforce revocation.
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/netbird"
BUILD = TOOLS / ".build"
ARCHES = {"amd64", "arm64"}
CREDENTIAL = re.compile(r"password|token|secret|setup.?key|private.?key", re.I)


def validate_config(value):
    schema = json.loads((TOOLS / "access.schema.json").read_text())
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as error:
        # Do not include the failing value: it could contain a credential.
        raise ValueError(
            f"config schema violation at {list(error.absolute_path)}"
        ) from None
    if not value["enabled"]:
        if value["destination"] is not None or value["sourceGroups"]:
            raise ValueError(
                "disabled configuration must clear destination and source groups"
            )
    else:
        if not value["destination"] or not value["sourceGroups"]:
            raise ValueError(
                "enabled access needs an explicit destination and source groups"
            )
        network = ipaddress.ip_network(value["destination"]["cidr"], strict=True)
        if network.version != 4 or network.prefixlen != 32:
            raise ValueError("only a dedicated IPv4 /32 HA destination is permitted")
        if (
            network.network_address.is_unspecified
            or network.network_address.is_multicast
        ):
            raise ValueError("invalid unicast destination")
        if any(
            group.casefold() in {"all", "*", "default"}
            for group in value["sourceGroups"]
        ):
            raise ValueError("unscoped source group")
    images = [image["image"] for image in value["images"]]
    if len(images) != len(set(images)):
        raise ValueError("duplicate image inventory entries")


def render(value):
    validate_config(value)
    enabled = value["enabled"]
    destination = value["destination"]
    return {
        "feature": value["feature"],
        "policy": {
            "enabled": enabled,
            "rules": [
                {
                    "sources": value["sourceGroups"],
                    "destinationCIDR": destination["cidr"],
                    "protocol": "tcp",
                    "ports": ["443"],
                    "bidirectional": False,
                }
            ]
            if enabled
            else [],
        },
        "dnsRecords": [
            {
                "name": destination["hostname"],
                "address": destination["cidr"].split("/")[0],
            }
        ]
        if enabled
        else [],
        "routes": [destination["cidr"]] if enabled else [],
    }


def validate_no_credentials(documents):
    def walk(value):
        if isinstance(value, dict):
            if value.get("kind") == "Secret" and (
                value.get("data") or value.get("stringData")
            ):
                raise ValueError("inline Kubernetes credential data is forbidden")
            if CREDENTIAL.search(str(value.get("name", ""))) and value.get("value"):
                raise ValueError("inline environment credential is forbidden")
            for key, child in value.items():
                # References are allowed; scalar credential values are not.
                if CREDENTIAL.search(key) and isinstance(child, str) and child:
                    if key not in {"secretName", "secretKey", "secretKeyRef"}:
                        raise ValueError("inline credential field is forbidden")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for document in documents:
        walk(document)


def validate_workloads(documents, value):
    inventory = {entry["image"]: set(entry["platforms"]) for entry in value["images"]}
    used = set()

    def walk(node):
        if isinstance(node, dict):
            if "containers" in node:
                selector = node.get("nodeSelector", {}).get("kubernetes.io/arch")
                possible = {selector} if selector else ARCHES
                if not possible <= ARCHES:
                    raise ValueError("unsupported node architecture")
                for container in (
                    node.get("containers", [])
                    + node.get("initContainers", [])
                    + node.get("ephemeralContainers", [])
                ):
                    image = container.get("image")
                    if image not in inventory:
                        raise ValueError("workload image missing from scan inventory")
                    used.add(image)
                    if not possible <= inventory[image]:
                        raise ValueError(
                            "image architecture requires an explicit compatible node selector"
                        )
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for document in documents:
        walk(document)
    if used != set(inventory):
        raise ValueError(
            "unused image inventory entry; scans must match actual workloads"
        )


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def docker_tool(tool, args, *, capture=False):
    image = json.loads((TOOLS / "toolchain.json").read_text())[tool]
    # No Docker socket or host credentials are mounted into scanners.
    command = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "-v",
        f"{ROOT / 'netbird'}:/work/netbird:ro",
        "-v",
        f"{BUILD}:/output",
        "-w",
        "/work",
        image,
        *args,
    ]
    return run(command, capture_output=capture, text=True)


def validate_schemas(path):
    relative = "/output/" + str(path.resolve().relative_to(BUILD.resolve()))
    version = json.loads((TOOLS / "toolchain.json").read_text())["kubernetesVersion"]
    docker_tool(
        "kubeconform",
        ["-strict", "-summary", "-kubernetes-version", version, str(relative)],
    )


def scan_images(value):
    for entry in value["images"]:
        for arch in entry["platforms"]:
            output = BUILD / "image-report.json"
            docker_tool(
                "trivy",
                [
                    "image",
                    "--image-src",
                    "remote",
                    "--platform",
                    f"linux/{arch}",
                    "--cache-dir",
                    "/output/trivy-cache",
                    "--scanners",
                    "vuln",
                    "--severity",
                    "HIGH,CRITICAL",
                    "--exit-code",
                    "1",
                    "--format",
                    "json",
                    "--output",
                    "/output/image-report.json",
                    entry["image"],
                ],
            )
            report = json.loads(output.read_text())
            image_config = report.get("Metadata", {}).get("ImageConfig", {})
            if (
                image_config.get("architecture") != arch
                or image_config.get("os") != "linux"
            ):
                raise ValueError(
                    "registry image platform does not match declared inventory"
                )
    if not value["images"]:
        print(
            "Image scan inventory: empty (no NetBird workload selected in Slice 1).",
            flush=True,
        )


def load_manifests(directory):
    documents = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if path.suffix not in {".yaml", ".yml", ".json"}:
            raise ValueError("unsupported manifest file; it must not escape validation")
        for document in yaml.safe_load_all(path.read_text()):
            if document is not None:
                if not isinstance(document, dict):
                    raise ValueError("manifest document must be an object")
                if document.get("kind") in {"Kustomization", "HelmRelease"}:
                    raise ValueError(
                        "templates/Helm must be rendered before entering the manifest gate"
                    )
                documents.append(document)
    return documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contracts-only",
        action="store_true",
        help="fast local check; not the CI gate",
    )
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    value = json.loads((ROOT / "netbird/access.json").read_text())
    validate_config(value)
    documents = load_manifests(ROOT / "netbird/manifests")
    validate_no_credentials(documents)
    validate_workloads(documents, value)
    (BUILD / "access-plan.json").write_text(json.dumps(render(value), indent=2) + "\n")
    manifests = BUILD / "manifests.yaml"
    manifests.write_text(yaml.safe_dump_all(documents, sort_keys=True))
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/netbird",
            "-m",
            "not tools",
            "-o",
            "cache_dir=tools/netbird/.build/pytest-cache",
        ]
    )
    if args.contracts_only:
        return
    run([sys.executable, "-m", "ruff", "check", "tools/netbird", "tests/netbird"])
    run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "tools/netbird",
            "tests/netbird",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "yamllint",
            "-c",
            "tools/netbird/yamllint.yaml",
            "netbird",
            ".github/workflows/validate-netbird.yaml",
        ]
    )
    if documents:
        validate_schemas(manifests)
    else:
        print(
            "Manifest inventory: empty; testing the schema gate with positive/negative fixtures.",
            flush=True,
        )
    docker_tool(
        "trivy",
        [
            "fs",
            "--scanners",
            "secret",
            "--exit-code",
            "1",
            "--no-progress",
            "--cache-dir",
            "/output/trivy-cache",
            "/work/netbird",
        ],
    )
    scan_images(value)
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/netbird",
            "-m",
            "tools",
            "-o",
            "cache_dir=tools/netbird/.build/pytest-cache",
        ]
    )
    print(
        "NetBird gate passed. This command did not apply resources or contact a cluster.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"NetBird gate failed: {error}", file=sys.stderr)
        sys.exit(1)
