"""Azure FinOps playbook as code: cost patterns, AI FinOps and a human-approved FinOps agent."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HOURS_PER_MONTH = 730  # Azure pricing convention: 730 hours in a billing month
SECONDS_PER_MONTH = HOURS_PER_MONTH * 3600
COMPANY = "Larkspur Freight (fictional)"
