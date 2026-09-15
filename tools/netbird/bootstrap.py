"""Render an undeployed bootstrap candidate; never apply or enroll anything."""

import copy
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = (
    "oci://ghcr.io/netbirdio/helm-charts/netbird-operator@"
    "sha256:d836ce83f06e7749f826a2ebe680bbec17a9545c7ed4645c4d6217a472d94b8d"
)


def restrict_secret_access(documents):
    documents = copy.deepcopy(documents)
    accounts = [
        d["metadata"]["name"] for d in documents if d["kind"] == "ServiceAccount"
    ]
    if accounts != ["netbird-operator"]:
        raise ValueError(
            "unexpected chart service accounts; review RBAC transformation"
        )
    secrets = []
    for document in documents:
        if document["kind"] != "ClusterRole":
            continue
        retained = []
        for rule in document.get("rules", []):
            resources = rule.get("resources", [])
            if "" in rule.get("apiGroups", []) or "*" in rule.get("apiGroups", []):
                if any(r == "*" or r.startswith("secrets/") for r in resources):
                    raise ValueError("unexpected wildcard or secret-subresource grant")
                if "secrets" in resources:
                    scoped = copy.deepcopy(rule)
                    scoped["resources"] = ["secrets"]
                    secrets.append(scoped)
                    rule["resources"] = [r for r in resources if r != "secrets"]
            if rule.get("resources") or rule.get("nonResourceURLs"):
                retained.append(rule)
        document["rules"] = retained
    if not secrets:
        raise ValueError("upstream Secret RBAC changed; review transformation")
    metadata = {"name": "netbird-operator-scoped-secrets", "namespace": "netbird"}
    documents.extend(
        [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "Role",
                "metadata": metadata,
                "rules": secrets,
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "RoleBinding",
                "metadata": copy.deepcopy(metadata),
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": metadata["name"],
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": accounts[0],
                        "namespace": "netbird",
                    }
                ],
            },
        ]
    )
    return documents


def main():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "netbird-operator",
            CHART,
            "--namespace",
            "netbird",
            "--values",
            str(ROOT / "netbird/bootstrap/operator-values.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = restrict_secret_access(
        [d for d in yaml.safe_load_all(rendered.stdout) if d]
    )
    # Helm normally sets the release namespace at install; make the file explicit.
    namespaced = {
        "ServiceAccount",
        "Role",
        "RoleBinding",
        "Service",
        "Deployment",
        "Certificate",
        "Issuer",
    }
    for document in documents:
        if document["kind"] in namespaced:
            document["metadata"].setdefault("namespace", "netbird")
    output = ROOT / "tools/netbird/.build/bootstrap-candidate.yaml"
    output.parent.mkdir(exist_ok=True)
    output.write_text(yaml.safe_dump_all(documents, sort_keys=False))
    print(
        f"Rendered candidate: {output}. Not deployment-approved; no resources applied."
    )


if __name__ == "__main__":
    main()
