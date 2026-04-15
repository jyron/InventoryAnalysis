"""Cross-source reconciliation.

Two jobs:
  1. Build a product master keyed by canonical SKU, pulling descriptive
     fields from the most-trusted source per field.
  2. Map e-commerce product IDs (separate namespace) to the master via
     fuzzy product-name matching, with a configurable threshold.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
from rapidfuzz import process, fuzz

from .config import ClientConfig, DEFAULT_CONFIG


def build_product_master(
    inventory: pd.DataFrame,
    pos: pd.DataFrame,
    cfg: ClientConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """One row per canonical SKU.

    Inventory is authoritative for cost/price/qty; POS supplies SKUs that
    inventory doesn't know about (useful for data-quality reporting).
    """
    inv = inventory.dropna(subset=["sku"]).copy()
    inv["source"] = "inventory"

    # SKUs seen in POS but not inventory — flagged as orphan products.
    pos_skus = pos.dropna(subset=["sku"])[["sku", "product_name"]].drop_duplicates("sku")
    missing = pos_skus[~pos_skus["sku"].isin(inv["sku"])].copy()
    missing["source"] = "pos_only"

    master = pd.concat([inv, missing], ignore_index=True, sort=False)
    return master


def map_ecommerce_to_master(
    ecommerce: pd.DataFrame,
    master: pd.DataFrame,
    cfg: ClientConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """Fuzzy-match each unique e-commerce product_name to a master SKU.

    Returns a dataframe with one row per unique ecom_product_id and the
    best match (or None if below threshold).
    """
    master_names = master.dropna(subset=["product_name", "sku"])[["sku", "product_name"]]
    choices = dict(zip(master_names["product_name"], master_names["sku"]))

    unique_ecom = (
        ecommerce.dropna(subset=["ecom_product_id", "product_name"])
        [["ecom_product_id", "product_name"]]
        .drop_duplicates("ecom_product_id")
    )

    rows = []
    for _, r in unique_ecom.iterrows():
        match = process.extractOne(
            r["product_name"], choices.keys(),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=cfg.fuzzy_match_threshold,
        )
        if match:
            name, score, _ = match
            rows.append({
                "ecom_product_id": r["ecom_product_id"],
                "ecom_product_name": r["product_name"],
                "matched_sku": choices[name],
                "matched_name": name,
                "match_score": score,
            })
        else:
            rows.append({
                "ecom_product_id": r["ecom_product_id"],
                "ecom_product_name": r["product_name"],
                "matched_sku": None,
                "matched_name": None,
                "match_score": None,
            })
    return pd.DataFrame(rows)


def reconcile_sources(
    pos: pd.DataFrame,
    inventory: pd.DataFrame,
    ecommerce: pd.DataFrame,
    cfg: ClientConfig = DEFAULT_CONFIG,
) -> dict:
    """End-to-end reconciliation. Returns a dict with the unified artifacts."""
    master = build_product_master(inventory, pos, cfg)
    ecom_map = map_ecommerce_to_master(ecommerce, master, cfg)
    ecommerce_keyed = ecommerce.merge(
        ecom_map[["ecom_product_id", "matched_sku", "match_score"]],
        on="ecom_product_id", how="left",
    ).rename(columns={"matched_sku": "sku"})
    return {
        "master": master,
        "ecom_map": ecom_map,
        "pos": pos,
        "inventory": inventory,
        "ecommerce": ecommerce_keyed,
    }
