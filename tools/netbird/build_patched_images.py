"""Build and scan pinned upstream sources before optionally publishing lab images."""

import argparse
import hashlib
import json
import subprocess
import tarfile
import urllib.request
from pathlib import Path

import gate

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    subprocess.run(args, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["operator", "peer"])
    parser.add_argument("architecture", choices=["amd64", "arm64"])
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    spec = json.loads((ROOT / "netbird/remediation/sources.json").read_text())[
        args.component
    ]
    work = gate.BUILD / "patched" / args.component
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "source.tar.gz"
    url = (
        f"https://api.github.com/repos/{spec['repository']}/tarball/{spec['revision']}"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec["archiveSha256"]:
        raise ValueError("upstream source archive checksum mismatch")
    with tarfile.open(archive) as bundle:
        roots = {member.name.split("/")[0] for member in bundle.getmembers()}
        if len(roots) != 1:
            raise ValueError("expected one upstream source root")
        bundle.extractall(work / "source", filter="data")
    source = work / "source" / roots.pop()
    image = f"ghcr.io/mrjson79/civilsnut-netbird-{args.component}:{spec['version']}-{args.architecture}"
    dockerfile = ROOT / "netbird/remediation" / f"{args.component.title()}.Dockerfile"
    run(
        "docker",
        "buildx",
        "build",
        "--platform",
        f"linux/{args.architecture}",
        "--load",
        "--tag",
        image,
        "--file",
        str(dockerfile),
        str(source),
    )
    image_archive = work / f"{args.architecture}.tar"
    report_path = work / f"{args.architecture}-scan.json"
    run("docker", "save", "--output", str(image_archive), image)
    gate.docker_tool(
        "trivy",
        [
            "image",
            "--input",
            "/output/" + str(image_archive.relative_to(gate.BUILD)),
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
            "/output/" + str(report_path.relative_to(gate.BUILD)),
        ],
    )
    report = json.loads(report_path.read_text())
    platform = report["Metadata"]["ImageConfig"]
    if (
        platform.get("architecture") != args.architecture
        or platform.get("os") != "linux"
    ):
        raise ValueError("built image platform mismatch")
    if args.push:
        run("docker", "push", image)
    print(f"Validated {image}; published={args.push}")


if __name__ == "__main__":
    main()
