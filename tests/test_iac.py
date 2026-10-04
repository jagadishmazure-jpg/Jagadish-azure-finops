"""Infrastructure and workflow structure, checked offline (no Terraform or Bicep binaries needed)."""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
POL = ROOT / "infra/policies"
WF = ROOT / ".github/workflows"


@pytest.mark.parametrize("name", ["require-tags", "allowed-vm-skus", "deny-untagged-public-ip"])
def test_policy_definition_shape(name):
    d = json.loads((POL / f"{name}.json").read_text())
    assert d["mode"] in {"All", "Indexed"}
    assert {"if", "then"} <= set(d["policyRule"])
    assert d["policyRule"]["then"]["effect"] == "[parameters('effect')]"
    eff = d["parameters"]["effect"]
    assert set(eff["allowedValues"]) >= {"Audit", "Deny"} and eff["defaultValue"] in eff["allowedValues"]


def test_required_tags_match_allocation_rules():
    rules = json.loads((ROOT / "data/allocation/rules.json").read_text())
    pol = (POL / "require-tags.json").read_text()
    for tag in rules["required_tags"]:
        assert tag in pol


def test_public_ip_policy_targets_public_ips_and_tags():
    t = (POL / "deny-untagged-public-ip.json").read_text()
    assert "Microsoft.Network/publicIPAddresses" in t and "cost-center" in t and "owner" in t


def test_terraform_and_bicep_load_the_same_policy_files():
    tf = (ROOT / "infra/terraform/locals.tf").read_text()
    bicep = (ROOT / "infra/bicep/modules/policies.bicep").read_text()
    for p in POL.glob("*.json"):
        assert p.name in tf and p.name in bicep


def test_smallest_settings():
    main = (ROOT / "infra/terraform/main.tf").read_text()
    assert 'account_replication_type        = "LRS"' in main or 'account_replication_type = "LRS"' in main
    assert "maximum = 2" in main
    variables = (ROOT / "infra/terraform/variables.tf").read_text()
    assert re.search(r'variable "deploy_autoscale_demo"[\s\S]*?default\s*=\s*false', variables)
    assert "monthly_budget        = 10" in (ROOT / "infra/terraform/envs/dev.tfvars").read_text()
    params = json.loads((ROOT / "infra/bicep/main.parameters.json").read_text())["parameters"]
    assert params.get("deployAutoscaleDemo", {"value": False})["value"] is False


def test_budget_notifications_include_forecast():
    locals_tf = (ROOT / "infra/terraform/locals.tf").read_text()
    assert '"Forecasted"' in locals_tf and '"Actual"' in locals_tf


def wf(name):
    return yaml.safe_load((WF / name).read_text())


def test_workflows_exist_and_parse():
    for n in ("ci.yml", "infra.yml", "deploy.yml", "teardown.yml"):
        assert isinstance(wf(n), dict)


def test_deploy_is_gated_and_uses_oidc():
    d = wf("deploy.yml")
    jobs = d["jobs"]
    for name in ("deploy-dev", "deploy-prod"):
        assert "vars.DEPLOY_ENABLED == 'true'" in jobs[name]["if"]
        assert jobs[name]["permissions"]["id-token"] == "write"
        assert any("azure/login" in s.get("uses", "") for s in jobs[name]["steps"])
    assert jobs["deploy-dev"]["environment"] == "dev" and jobs["deploy-prod"]["environment"] == "prod"
    assert jobs["deploy-prod"]["needs"] == "deploy-dev"
    on = d[True] if True in d else d["on"]
    assert on["workflow_dispatch"]["inputs"]["deploy_tool"]["options"] == ["terraform", "bicep"]
    text = (WF / "deploy.yml").read_text()
    assert "client-secret" not in text and "AZURE_CREDENTIALS" not in text


def test_teardown_needs_gate_and_confirmation():
    t = wf("teardown.yml")["jobs"]["teardown"]
    assert "vars.DEPLOY_ENABLED == 'true'" in t["if"] and "inputs.confirm == inputs.environment" in t["if"]


def test_ci_runs_drift_checks():
    text = (WF / "ci.yml").read_text()
    for cmd in (
        "pytest",
        "generate_data.py --check",
        "render_docs.py --check",
        "bicep build",
        "ruff format --check",
    ):
        assert cmd in text


def test_checkov_skips_are_justified():
    lines = (ROOT / ".checkov.yaml").read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("- CKV"):
            assert lines[i - 1].strip().startswith("#"), f"unjustified skip {line.strip()}"


def test_queries_are_present_for_every_pattern():
    text = " ".join(p.read_text() for p in (ROOT / "queries").rglob("*.kql"))
    for n in range(1, 11):
        assert re.search(rf"Patterns? [\d, and]*\b{n}\b", text), f"no query mentions pattern {n}"


def test_assignments_pass_the_environment_effect():
    tf = (ROOT / "infra/terraform/locals.tf").read_text() + (ROOT / "infra/terraform/main.tf").read_text()
    bicep = (ROOT / "infra/bicep/modules/guardrails.bicep").read_text()
    assert "var.policy_effect" in tf and "policyEffect" in bicep
    assert 'policy_effect         = "Audit"' in (ROOT / "infra/terraform/envs/dev.tfvars").read_text()
    assert 'policy_effect         = "Deny"' in (ROOT / "infra/terraform/envs/prod.tfvars").read_text()
