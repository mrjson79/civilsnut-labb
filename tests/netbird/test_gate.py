"""Access contracts: exercise unsafe changes, not implementation details."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "netbird_gate", ROOT / "tools/netbird/gate.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def config():
    return {
        "schemaVersion": 1,
        "feature": "netbird-home-assistant-access",
        "enabled": False,
        "destination": None,
        "sourceGroups": [],
        "images": [],
    }


def enabled_config():
    value = config()
    value.update(
        enabled=True,
        destination={
            "cidr": "192.0.2.10/32",
            "hostname": "ha-vpn.civilsnut.se",
            "ports": [443],
        },
        sourceGroups=["test-pilot-group"],
    )
    return value


def test_netbird_off_grants_no_access():
    rendered = gate.render(config())
    assert rendered["policy"]["enabled"] is False
    assert rendered["policy"]["rules"] == []
    assert rendered["dnsRecords"] == []
    assert rendered["routes"] == []


def test_off_cannot_retain_membership_or_destination():
    value = enabled_config()
    value["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        gate.validate_config(value)


def test_enabled_grants_only_dedicated_ha_tcp_443():
    rendered = gate.render(enabled_config())
    assert rendered["policy"]["enabled"] is True
    rule = rendered["policy"]["rules"][0]
    assert rule["protocol"] == "tcp"
    assert rule["ports"] == ["443"]
    assert rule["bidirectional"] is False
    assert rendered["routes"] == ["192.0.2.10/32"]


@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "192.168.1.0/24", "10.0.0.0/8", "::/0"])
def test_broad_routes_rejected(cidr):
    value = enabled_config()
    value["destination"]["cidr"] = cidr
    with pytest.raises(ValueError, match="/32"):
        gate.validate_config(value)


@pytest.mark.parametrize("ports", [[80], [443, 8123], [22]])
def test_other_ports_rejected(ports):
    value = enabled_config()
    value["destination"]["ports"] = ports
    with pytest.raises(ValueError):
        gate.validate_config(value)


@pytest.mark.parametrize("groups", [[], ["All"], ["all"]])
def test_unscoped_sources_rejected(groups):
    value = enabled_config()
    value["sourceGroups"] = groups
    with pytest.raises(ValueError):
        gate.validate_config(value)


def test_unknown_config_fields_fail_closed():
    value = config()
    value["setupKey"] = "synthetic-test-credential"
    with pytest.raises(ValueError):
        gate.validate_config(value)


def test_selected_images_must_be_immutable():
    value = config()
    value["images"] = [
        {"image": "example.invalid/netbird:latest", "platforms": ["amd64"]}
    ]
    with pytest.raises(ValueError):
        gate.validate_config(value)


def deployment(image, arch=None):
    spec = {"containers": [{"name": "peer", "image": image}]}
    if arch:
        spec["nodeSelector"] = {"kubernetes.io/arch": arch}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "peer"},
        "spec": {"template": {"spec": spec}},
    }


def test_uninventoried_image_rejected():
    with pytest.raises(ValueError, match="inventory"):
        gate.validate_workloads([deployment("example.invalid/peer:1")], config())


def test_amd64_only_image_requires_node_selector():
    value = config()
    image = "example.invalid/peer@sha256:" + "a" * 64
    value["images"] = [{"image": image, "platforms": ["amd64"]}]
    with pytest.raises(ValueError, match="architecture"):
        gate.validate_workloads([deployment(image)], value)
    gate.validate_workloads([deployment(image, "amd64")], value)


def test_inventory_cannot_silently_skip_unused_image():
    value = config()
    value["images"] = [
        {"image": "example.invalid/peer@sha256:" + "a" * 64, "platforms": ["amd64"]}
    ]
    with pytest.raises(ValueError, match="unused"):
        gate.validate_workloads([], value)


@pytest.mark.parametrize(
    "document",
    [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "x"},
            "stringData": {"setup-key": "synthetic-secret"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "x"},
            "data": {"setup-key": "c3ludGhldGljLXNlY3JldA=="},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "x"},
            "data": {"NB_SETUP_KEY": "synthetic-secret"},
        },
    ],
)
def test_plaintext_or_encoded_credentials_rejected(document):
    with pytest.raises(ValueError, match="credential"):
        gate.validate_no_credentials([document])


def test_env_secret_reference_allowed_but_inline_key_rejected():
    document = deployment("example.invalid/peer:1")
    container = document["spec"]["template"]["spec"]["containers"][0]
    container["env"] = [
        {
            "name": "NB_SETUP_KEY",
            "valueFrom": {"secretKeyRef": {"name": "x", "key": "key"}},
        }
    ]
    gate.validate_no_credentials([document])
    unsafe = copy.deepcopy(document)
    unsafe["spec"]["template"]["spec"]["containers"][0]["env"][0] = {
        "name": "NB_SETUP_KEY",
        "value": "synthetic-secret",
    }
    with pytest.raises(ValueError, match="credential"):
        gate.validate_no_credentials([unsafe])


def test_off_cannot_inject_an_allow_policy():
    value = config()
    value["policy"] = {"enabled": True, "rules": [{"action": "accept"}]}
    with pytest.raises(ValueError):
        gate.validate_config(value)
