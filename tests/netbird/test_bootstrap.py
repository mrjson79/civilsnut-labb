"""Regression for the chart's ineffective allowAllSecrets=false setting."""

import importlib.util

import pytest

from test_gate import ROOT

SPEC = importlib.util.spec_from_file_location(
    "bootstrap", ROOT / "tools/netbird/bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_secret_permissions_move_to_netbird_namespace():
    documents = [
        {"kind": "ServiceAccount", "metadata": {"name": "netbird-operator"}},
        {
            "kind": "ClusterRole",
            "metadata": {"name": "netbird-operator"},
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["secrets", "pods"],
                    "verbs": ["get", "list"],
                },
            ],
        },
    ]
    result = bootstrap.restrict_secret_access(documents)
    cluster = next(x for x in result if x["kind"] == "ClusterRole")
    assert cluster["rules"][0]["resources"] == ["pods"]
    role = next(x for x in result if x["kind"] == "Role")
    assert role["metadata"]["namespace"] == "netbird"
    assert role["rules"][0]["resources"] == ["secrets"]
    binding = next(x for x in result if x["kind"] == "RoleBinding")
    assert binding["subjects"][0]["namespace"] == "netbird"


@pytest.mark.parametrize("resource", ["*", "secrets/status"])
def test_unexpected_secret_grants_fail_closed(resource):
    with pytest.raises(ValueError):
        bootstrap.restrict_secret_access(
            [
                {"kind": "ServiceAccount", "metadata": {"name": "netbird-operator"}},
                {
                    "kind": "ClusterRole",
                    "rules": [
                        {"apiGroups": [""], "resources": [resource], "verbs": ["*"]}
                    ],
                },
            ]
        )
