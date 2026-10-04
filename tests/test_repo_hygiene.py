"""Repository hygiene: docs complete and current, no dates, no secrets or real identifiers."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", ".terraform", "refs"}
MD = sorted(p for p in ROOT.rglob("*.md") if not SKIP_PARTS & set(p.parts))
SECTIONS = [
    "Problem",
    "Signals and data sources",
    "Detection logic",
    "Decision rule",
    "Worked example",
    "Savings math",
    "Risks and guardrails",
    "Automation and approval flow",
    "IaC and policy",
    "Observability and KQL",
    "Mapping to Azure tools",
    "Limitations",
    "Interview talking points",
]
PATTERN_DOCS = sorted((ROOT / "docs/patterns").glob("[0-9][0-9]-*.md"))
MONTHS = r"\b(January|February|March|April|June|July|August|September|October|November|December)\b"
TEXT_FILES = [
    p
    for p in ROOT.rglob("*")
    if p.is_file()
    and not SKIP_PARTS & set(p.parts)
    and p.suffix
    in {
        ".md",
        ".py",
        ".json",
        ".yml",
        ".tf",
        ".bicep",
        ".kql",
        ".hcl",
        ".sh",
        ".toml",
        ".csv",
        ".jsonl",
        ".tfvars",
    }
]


def folders():
    yield from sorted({p.parent for p in ROOT.rglob("*") if p.is_file() and not SKIP_PARTS & set(p.parts)})


@pytest.mark.parametrize("folder", list(folders()), ids=lambda p: str(p.relative_to(ROOT)) or ".")
def test_every_folder_has_a_readme_with_a_file_table(folder):
    readme = folder / "README.md"
    assert readme.exists(), f"{folder} has no README.md"
    if folder != ROOT:
        assert "| File | What it does |" in readme.read_text()


def test_folder_readmes_list_every_file():
    for readme in ROOT.rglob("README.md"):
        if SKIP_PARTS & set(readme.parts) or readme.parent == ROOT:
            continue
        text = readme.read_text()
        for child in readme.parent.iterdir():
            if (
                child.name in {"README.md", "__pycache__", ".terraform", ".terraform.lock.hcl"}
                or child.name.endswith(".approval.json")
                or child.name.endswith(".plan.json")
            ):
                continue
            name = child.name + ("/" if child.is_dir() else "")
            assert f"`{name}`" in text, f"{readme.relative_to(ROOT)} does not list {name}"


def test_no_dates_in_markdown():
    for p in MD:
        t = p.read_text()
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", t), f"ISO date in {p}"
        assert not re.search(r"(?<![\d$,.])20[1-3]\d(?![\d,.%])", t), f"year in {p}"
        assert not re.search(MONTHS, t), f"month name in {p}"
        assert "Date:" not in t, f"Date line in {p}"


@pytest.mark.parametrize("doc", PATTERN_DOCS, ids=lambda p: p.name)
def test_pattern_doc_has_all_sections_in_order(doc):
    t = doc.read_text()
    pos = [t.find(f"## {i}. {s}") for i, s in enumerate(SECTIONS, 1)]
    assert all(x >= 0 for x in pos), [s for s, x in zip(SECTIONS, pos, strict=True) if x < 0]
    assert pos == sorted(pos)
    assert "<!-- output:" in t and "<!-- code:" in t
    assert "```mermaid" in t


def test_ten_pattern_docs_match_the_mcp_doc_links():
    from finops.agent.mcp_server import doc_for
    from finops.patterns import MODULES

    assert len(PATTERN_DOCS) == 10
    for m in MODULES:
        pattern = m.split("_", 1)[0] + "-" + m.split("_", 1)[1].replace("_", "-")
        assert (ROOT / doc_for(pattern)).exists(), pattern


def test_doc_outputs_and_excerpts_are_current():
    r = subprocess.run(
        [sys.executable, "scripts/render_docs.py", "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_secrets_or_real_identifiers():
    guid = re.compile(r"\b(?!00000000-)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    bad = [
        re.compile(p, re.I)
        for p in (
            r"AccountKey=",
            r"-----BEGIN",
            r"client_secret\s*=",
            r"@gmail\.com",
            r"meijer",
            r"datasparx",
        )
    ]
    for p in TEXT_FILES:
        if p.name == "test_repo_hygiene.py":
            continue
        t = p.read_text(errors="ignore")
        if p.name != "retail-prices-snapshot.json":
            assert not guid.search(t), f"GUID-like identifier in {p}"
        for b in bad:
            assert not b.search(t), f"{b.pattern} in {p}"


def test_company_is_fictional_everywhere():
    readme = (ROOT / "README.md").read_text()
    assert "Larkspur Freight" in readme and "fictional" in readme


def test_changelog_has_only_unreleased():
    t = (ROOT / "CHANGELOG.md").read_text()
    versions = re.findall(r"^## (.+)$", t, re.M)
    assert versions == ["Unreleased"]


def test_six_adrs_without_date_lines():
    adrs = sorted((ROOT / "docs/adr").glob("0*.md"))
    assert len(adrs) == 6
    for a in adrs:
        t = a.read_text()
        assert "**Status:**" in t and "Date" not in t


def test_readme_has_recruiter_section_and_estimate_labels():
    t = (ROOT / "README.md").read_text()
    assert "## At a glance (for recruiters)" in t
    assert "list-price snapshot" in t and "(estimate)" in t
