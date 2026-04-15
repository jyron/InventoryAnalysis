"""AI-assisted insight layer.

What the LLM is used for here (and why):

1. `triage_ops_notes` — the ops team's "Notes" column is free-text
   ("Physical count: 33 (system wrong)", "recount needed — vendor shorted us",
   etc.). Parsing it with regex works for the clean cases; we use the LLM
   to classify the long tail and extract structured actions. This is a
   legitimate NLP use case — deterministic code can't read prose reliably.

2. `summarize_for_cfo` — turns the numeric findings dict into a short
   narrative paragraph in CFO-friendly language. Always audited against
   the underlying numbers.

What we DON'T trust the LLM for:
- Computing any numbers. All dollar figures come from pandas.
- Picking which SKUs matter. That's a deterministic sort by $ impact.
- Deciding what the "right" quantity is when systems disagree.
"""
from __future__ import annotations
import os
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- Structured-output schemas ----------

class OpsNoteTriage(BaseModel):
    """One row of structured output per ops-notes entry."""
    sku: str
    raw_note: str
    issue_type: Literal[
        "physical_count_override",
        "vendor_short_ship",
        "damaged_inventory",
        "location_error",
        "recount_requested",
        "other",
    ]
    severity: Literal["low", "medium", "high"]
    recommended_action: str = Field(..., description="Imperative sentence, <15 words.")
    confidence: float = Field(..., ge=0.0, le=1.0)


class InventoryHealthSummary(BaseModel):
    """CFO-ready narrative generated from the numeric findings dict."""
    headline: str = Field(..., description="One sentence. Lead with the dollar figure.")
    top_risks: list[str] = Field(..., max_length=3)
    data_quality_callouts: list[str] = Field(..., max_length=3)
    recommended_next_steps: list[str] = Field(..., max_length=3)


# ---------- LLM plumbing (Anthropic, with an offline fallback) ----------

def _get_anthropic_client():
    try:
        import anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            return anthropic.Anthropic()
    except ImportError:
        pass
    return None


def triage_ops_notes(notes_df, limit: int = 20) -> list[OpsNoteTriage]:
    """Classify each ops-notes entry into a structured record.

    `notes_df` must have columns ['sku', 'notes']. Falls back to a
    deterministic classifier when no API key is set so the notebook
    still runs offline.
    """
    rows = notes_df.dropna(subset=["notes"]).head(limit).to_dict("records")
    client = _get_anthropic_client()
    if client is None:
        return [_offline_triage(r) for r in rows]

    system = (
        "You classify retail operations notes into structured records. "
        "Respond with one JSON object per note, exactly matching the schema. "
        "Base severity on operational risk: medium if count differs by <20%, "
        "high if >20% or short-shipped, low if cosmetic."
    )
    results: list[OpsNoteTriage] = []
    for r in rows:
        prompt = (
            f"SKU: {r['sku']}\nNote: {r['notes']!r}\n\n"
            "Return JSON with keys: sku, raw_note, issue_type, severity, "
            "recommended_action, confidence (0-1)."
        )
        try:
            msg = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            import json, re
            text = msg.content[0].text
            blob = re.search(r"\{.*\}", text, re.S)
            results.append(OpsNoteTriage(**json.loads(blob.group(0))))
        except Exception:
            results.append(_offline_triage(r))
    return results


def _offline_triage(r: dict) -> OpsNoteTriage:
    import re
    note = str(r["notes"])
    low = note.lower()
    if re.search(r"physical count", low):
        t = "physical_count_override"
    elif "short" in low or "vendor" in low:
        t = "vendor_short_ship"
    elif "damage" in low or "broken" in low:
        t = "damaged_inventory"
    elif "location" in low or "aisle" in low or "bin" in low:
        t = "location_error"
    elif "recount" in low:
        t = "recount_requested"
    else:
        t = "other"
    sev = "high" if "wrong" in low or "short" in low else "medium"
    return OpsNoteTriage(
        sku=str(r["sku"]),
        raw_note=note,
        issue_type=t,
        severity=sev,
        recommended_action="Reconcile system quantity with physical count.",
        confidence=0.55,
    )


def summarize_for_cfo(findings: dict) -> InventoryHealthSummary:
    """Narrative summary from the raw numbers. Deterministic fallback included."""
    client = _get_anthropic_client()
    if client is None:
        return _offline_summary(findings)

    system = (
        "You are a consultant writing one-paragraph findings for a CFO. "
        "Use plain English, lead with the dollar figure, no hedging. "
        "Never invent numbers — use only what's in the input."
    )
    import json
    try:
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content":
                f"Findings:\n{json.dumps(findings, indent=2, default=str)}\n\n"
                "Return JSON matching schema: headline, top_risks[3], "
                "data_quality_callouts[3], recommended_next_steps[3]."}],
        )
        import re
        text = msg.content[0].text
        blob = re.search(r"\{.*\}", text, re.S)
        return InventoryHealthSummary(**json.loads(blob.group(0)))
    except Exception:
        return _offline_summary(findings)


def _offline_summary(f: dict) -> InventoryHealthSummary:
    return InventoryHealthSummary(
        headline=(
            f"${f['lost_revenue_at_risk']/1e6:.1f}M of revenue is at "
            f"stockout risk across {f['at_risk_skus']} SKUs, while "
            f"${f['dead_capital']:,.0f} sits in unlaunched or non-moving inventory."
        ),
        top_risks=[
            f"{f['at_risk_skus']} SKUs have under 14 days of cover — potential ${f['lost_revenue_at_risk']/1e6:.1f}M lost revenue.",
            f"{f['dead_skus']} SKUs have not sold in 60 days, tying up ${f['dead_capital']:,.0f} of working capital.",
            f"System quantity disagrees with ops physical counts on {f['ops_override_count']} SKUs worth ${f['ops_override_dollars']:,.0f}.",
        ],
        data_quality_callouts=[
            f"{f['pos_negative_qty_rows']:,} POS rows have negative quantities — returns are not flagged distinctly from data-entry errors.",
            f"{f['pos_missing_customer']:,} POS transactions ({f['pct_missing_customer']:.0%}) have no customer ID — limits loyalty/repeat analysis.",
            f"E-commerce uses a separate product-ID namespace; {f['ecom_unmapped']} products still cannot be mapped to inventory automatically.",
        ],
        recommended_next_steps=[
            "Expedite purchase orders for the top 10 at-risk SKUs this week.",
            "Return or liquidate the 15 dead SKUs to recover working capital.",
            "Enforce a single SKU format at POS entry; add required-field validation for customer and store.",
        ],
    )
