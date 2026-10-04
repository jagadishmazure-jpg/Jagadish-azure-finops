"""Provisioned throughput (PTU) vs pay-as-you-go break-even.

PTUs buy reserved model throughput by the hour. They pay off only at high, steady utilization.

ASSUMPTIONS (verify with the Azure OpenAI capacity calculator for your model and deployment type):
  * gpt-4o global provisioned: 2,500 input tokens per minute per PTU; one output token uses the
    capacity of 4 input tokens; minimum 15 PTUs, then steps of 5;
  * the busiest minute carries ``PEAK_FACTOR`` times the average minute (business-hours traffic);
  * hourly PTU list price from the snapshot (monthly and yearly PTU reservations are cheaper and
    are not in the snapshot).
"""

from __future__ import annotations

import math
from typing import Any

from finops import HOURS_PER_MONTH
from finops.pricing import default_book

TPM_PER_PTU = 2500  # ASSUMPTION
OUTPUT_WEIGHT = 4  # ASSUMPTION
MIN_PTU, STEP = 15, 5  # ASSUMPTION
PEAK_FACTOR = 3.0  # ASSUMPTION
MINUTES_PER_MONTH = HOURS_PER_MONTH * 60


def ptus_for(peak_tpm: float) -> int:
    n = max(MIN_PTU, math.ceil(peak_tpm / TPM_PER_PTU))
    return MIN_PTU + math.ceil((n - MIN_PTU) / STEP) * STEP


def decision(payg_monthly: float, ptu_monthly: float, breakeven_utilization: float) -> str:
    if breakeven_utilization > 1:
        return "stay pay-as-you-go (hourly PTU cannot break even even at 100% utilization; use PTU only for latency guarantees or with a PTU reservation)"
    if payg_monthly < ptu_monthly:
        return "stay pay-as-you-go"
    return "move steady load to PTU, burst to pay-as-you-go"


def analyze(input_tokens: float, output_tokens: float, payg_monthly: float) -> dict[str, Any]:
    book = default_book()
    equiv = input_tokens + OUTPUT_WEIGHT * output_tokens
    avg_tpm = equiv / MINUTES_PER_MONTH
    peak_tpm = avg_tpm * PEAK_FACTOR
    n = ptus_for(peak_tpm)
    ptu_monthly = n * book.price("aoai.ptu.global_hour") * HOURS_PER_MONTH
    capacity = n * TPM_PER_PTU * MINUTES_PER_MONTH
    utilization = equiv / capacity
    # PAYG cost per input-equivalent token at today's mix, and the volume where PTU breaks even
    payg_per_equiv = payg_monthly / equiv
    breakeven_equiv = ptu_monthly / payg_per_equiv
    return {
        "monthly_input_tokens": round(input_tokens), "monthly_output_tokens": round(output_tokens),
        "avg_tpm": round(avg_tpm), "peak_tpm": round(peak_tpm), "ptus": n,
        "ptu_monthly": round(ptu_monthly, 2), "payg_monthly": round(payg_monthly, 2),
        "utilization_pct": round(100 * utilization, 2),
        "breakeven_volume_multiple": round(breakeven_equiv / equiv, 1),
        "breakeven_utilization_pct": round(100 * breakeven_equiv / capacity, 1),
        "decision": decision(payg_monthly, ptu_monthly, breakeven_equiv / capacity),
    }
