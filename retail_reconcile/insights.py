"""Inventory health analytics.

All functions take the reconciled artifacts dict from `reconcile_sources`
and return a pandas DataFrame. None of these touch files or talk to LLMs.
"""
from __future__ import annotations
import re
from datetime import timedelta
from typing import Optional

import pandas as pd

from .config import ClientConfig, DEFAULT_CONFIG


def _total_sales(pos: pd.DataFrame, ecommerce: pd.DataFrame) -> pd.DataFrame:
    """Units sold per SKU across both channels.

    Negative POS quantities are treated as returns (netted), which matches
    how the client's POS exports them.
    """
    pos_sales = (
        pos.dropna(subset=["sku", "date"])
        .groupby("sku", as_index=False)
        .agg(pos_units=("quantity", "sum"),
             pos_revenue=("unit_price", lambda s: (s * pos.loc[s.index, "quantity"]).sum()),
             pos_last_sale=("date", "max"),
             pos_first_sale=("date", "min"))
    )
    ecom_sales = (
        ecommerce.dropna(subset=["sku"])
        .query("status != 'cancelled'")
        .groupby("sku", as_index=False)
        .agg(ecom_units=("quantity", "sum"),
             ecom_revenue=("total", "sum"),
             ecom_last_sale=("order_date", "max"))
    )
    return pos_sales.merge(ecom_sales, on="sku", how="outer")


def stockout_risk(artifacts: dict, cfg: ClientConfig = DEFAULT_CONFIG,
                  snapshot_date=None) -> pd.DataFrame:
    """Items with less than N days of forward cover at recent velocity.

    Velocity = last-30-days units sold per day (both channels combined).
    Forward cover = qty_on_hand / velocity.
    """
    pos = artifacts["pos"]
    inv = artifacts["inventory"]
    ecom = artifacts["ecommerce"]

    if snapshot_date is None:
        snapshot_date = max(
            pos["date"].dropna().max(),
            ecom["order_date"].dropna().max(),
        )
    window_start = snapshot_date - timedelta(days=30)

    pos_recent = pos[(pos["date"] >= window_start) & (pos["quantity"] > 0)]
    ecom_recent = ecom[(ecom["order_date"] >= window_start) & (ecom["status"] != "cancelled")]

    vel = (
        pd.concat([
            pos_recent[["sku", "quantity"]],
            ecom_recent[["sku", "quantity"]],
        ], ignore_index=True)
        .dropna(subset=["sku"])
        .groupby("sku", as_index=False)["quantity"].sum()
        .rename(columns={"quantity": "units_30d"})
    )
    vel["daily_velocity"] = vel["units_30d"] / 30.0

    merged = inv.merge(vel, on="sku", how="left")
    merged["daily_velocity"] = merged["daily_velocity"].fillna(0)
    merged["days_cover"] = merged.apply(
        lambda r: (r["qty_on_hand"] / r["daily_velocity"]) if r["daily_velocity"] > 0 else float("inf"),
        axis=1,
    )
    at_risk = merged[
        (merged["daily_velocity"] > 0)
        & (merged["days_cover"] < cfg.stockout_days_cover_threshold)
    ].copy()
    at_risk["lost_revenue_30d_if_out"] = (
        at_risk["daily_velocity"] * 30 * at_risk["retail_price"]
    ).round(2)
    return at_risk.sort_values("days_cover")[
        ["sku", "product_name", "qty_on_hand", "reorder_level",
         "units_30d", "daily_velocity", "days_cover",
         "retail_price", "lost_revenue_30d_if_out"]
    ]


def dead_inventory(artifacts: dict, cfg: ClientConfig = DEFAULT_CONFIG,
                   snapshot_date=None) -> pd.DataFrame:
    """SKUs with stock on hand and no sale in the configured window."""
    inv = artifacts["inventory"]
    sales = _total_sales(artifacts["pos"], artifacts["ecommerce"])

    if snapshot_date is None:
        snapshot_date = max(
            artifacts["pos"]["date"].dropna().max(),
            artifacts["ecommerce"]["order_date"].dropna().max(),
        )
    cutoff = snapshot_date - timedelta(days=cfg.dead_inventory_days)

    merged = inv.merge(sales, on="sku", how="left")
    merged["pos_last_sale"] = pd.to_datetime(merged["pos_last_sale"], errors="coerce")
    merged["ecom_last_sale"] = pd.to_datetime(merged["ecom_last_sale"], errors="coerce")
    last_sale = merged[["pos_last_sale", "ecom_last_sale"]].max(axis=1)
    merged["last_sale"] = last_sale
    cutoff = pd.Timestamp(cutoff)
    dead = merged[
        (merged["qty_on_hand"] > 0)
        & ((last_sale.isna()) | (last_sale < cutoff))
    ].copy()
    dead["capital_tied_up"] = (dead["qty_on_hand"] * dead["unit_cost"]).round(2)
    dead["days_since_sale"] = (
        pd.to_datetime(snapshot_date) - pd.to_datetime(dead["last_sale"])
    ).dt.days
    return dead.sort_values("capital_tied_up", ascending=False)[
        ["sku", "product_name", "category", "qty_on_hand", "unit_cost",
         "capital_tied_up", "last_sale", "days_since_sale"]
    ]


def reconciliation_gaps(artifacts: dict, cfg: ClientConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Surface the hard cases: disagreements that matter in dollars.

    Two kinds tracked here:
      1. Notes-column overrides where ops wrote a physical count that
         differs from the system qty_on_hand.
      2. POS SKUs that don't exist in the inventory master (orphan sales).
    """
    inv = artifacts["inventory"].copy()
    pos = artifacts["pos"]

    gaps = []
    note_re = re.compile(r"physical count:\s*(\d+)", re.I)
    for _, r in inv.iterrows():
        if pd.isna(r.get("notes")):
            continue
        m = note_re.search(str(r["notes"]))
        if not m:
            continue
        physical = int(m.group(1))
        sys_qty = r["qty_on_hand"] or 0
        delta = physical - sys_qty
        gaps.append({
            "sku": r["sku"],
            "product_name": r["product_name"],
            "system_qty": sys_qty,
            "ops_physical_count": physical,
            "delta_units": delta,
            "dollar_impact": round(abs(delta) * (r["unit_cost"] or 0), 2),
            "gap_type": "ops_override",
            "evidence": str(r["notes"]),
        })

    inv_skus = set(inv.dropna(subset=["sku"])["sku"])
    pos_orphan_revenue = (
        pos.dropna(subset=["sku"])
        .loc[~pos["sku"].isin(inv_skus)]
        .assign(rev=lambda d: d["quantity"] * d["unit_price"])
        .groupby(["sku", "product_name"], as_index=False)
        .agg(orphan_revenue=("rev", "sum"), txn_count=("transaction_id", "nunique"))
        .sort_values("orphan_revenue", ascending=False)
    )
    for _, r in pos_orphan_revenue.head(50).iterrows():
        gaps.append({
            "sku": r["sku"],
            "product_name": r["product_name"],
            "system_qty": None,
            "ops_physical_count": None,
            "delta_units": None,
            "dollar_impact": round(r["orphan_revenue"], 2),
            "gap_type": "pos_orphan",
            "evidence": f"{int(r['txn_count'])} POS transactions, ${r['orphan_revenue']:.0f} revenue, no inventory record",
        })

    return pd.DataFrame(gaps).sort_values("dollar_impact", ascending=False)


def channel_performance(artifacts: dict) -> pd.DataFrame:
    """In-store vs online split, at SKU-category and overall level."""
    inv = artifacts["inventory"][["sku", "category", "retail_price"]]

    pos_rev = (
        artifacts["pos"].assign(rev=lambda d: d["quantity"] * d["unit_price"])
        .groupby("sku", as_index=False)["rev"].sum()
        .rename(columns={"rev": "instore_revenue"})
    )
    ecom_rev = (
        artifacts["ecommerce"].query("status != 'cancelled'")
        .groupby("sku", as_index=False)["total"].sum()
        .rename(columns={"total": "online_revenue"})
    )
    merged = inv.merge(pos_rev, on="sku", how="left").merge(ecom_rev, on="sku", how="left")
    merged[["instore_revenue", "online_revenue"]] = merged[["instore_revenue", "online_revenue"]].fillna(0)

    by_cat = merged.groupby("category", as_index=False).agg(
        instore=("instore_revenue", "sum"),
        online=("online_revenue", "sum"),
    )
    by_cat["total"] = by_cat["instore"] + by_cat["online"]
    by_cat["online_share"] = (by_cat["online"] / by_cat["total"]).round(3)
    return by_cat.sort_values("total", ascending=False)


def data_quality_report(artifacts: dict) -> dict:
    """Counts of the issues the client should go fix in their systems."""
    pos = artifacts["pos"]
    inv = artifacts["inventory"]
    ecom = artifacts["ecommerce"]
    ecom_map = artifacts["ecom_map"]

    pos_issues = {
        "total_rows": len(pos),
        "missing_sku": int(pos["sku"].isna().sum()),
        "missing_store": int(pos["store_id"].isna().sum()),
        "missing_customer": int(pos["customer_id"].isna().sum()),
        "negative_quantity_rows": int((pos["quantity"] < 0).sum()),
        "unparseable_date": int(pos["date"].isna().sum()),
        "orphan_skus_vs_inventory": int(
            pos.dropna(subset=["sku"])
            .loc[~pos["sku"].isin(inv["sku"].dropna())]["sku"].nunique()
        ),
    }
    ecom_issues = {
        "unique_products": int(ecom_map["ecom_product_id"].nunique()),
        "mapped_to_sku": int(ecom_map["matched_sku"].notna().sum()),
        "unmapped": int(ecom_map["matched_sku"].isna().sum()),
    }
    inv_issues = {
        "skus": int(inv["sku"].notna().sum()),
        "rows_with_ops_notes": int(inv["notes"].notna().sum()),
        "missing_reorder_level": int(inv["reorder_level"].isna().sum()),
    }
    return {"pos": pos_issues, "ecommerce": ecom_issues, "inventory": inv_issues}
