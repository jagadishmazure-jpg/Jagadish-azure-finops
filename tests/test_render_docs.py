"""The doc renderer: output blocks and code excerpts."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_docs", ROOT / "scripts/render_docs.py")
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)


def test_output_block_is_filled_from_the_cli():
    text = "<!-- output: pattern p08 -->\nstale\n<!-- /output -->\n"
    out = rd.render(text)
    assert "TOTAL: 6 finding(s)" in out and "stale" not in out


def test_python_excerpt_is_the_current_function():
    lang, body = rd.excerpt("src/finops/patterns/base.py::percentile")
    assert lang == "python" and body.startswith("def percentile")


def test_constant_excerpt():
    _, body = rd.excerpt("src/finops/patterns/p01_rightsize.py::RULE")
    assert body.startswith("RULE = {")


def test_hcl_block_excerpt_balances_braces():
    lang, body = rd.excerpt('infra/terraform/main.tf::resource "azurerm_storage_management_policy"')
    assert lang == "hcl" and body.count("{") == body.count("}")


def test_unknown_name_fails():
    with pytest.raises(SystemExit):
        rd.excerpt("src/finops/patterns/base.py::nope")
