"""Source loaders.

Each loader is responsible for reading its source format and emitting a
canonical pandas DataFrame with a documented schema. The rest of the
pipeline never touches raw files.

Canonical schemas
-----------------
POS transactions (`load_pos`):
    transaction_id, date (datetime.date), sku_raw, sku, product_name,
    quantity (float), unit_price (float), store_id, customer_id, payment_method

Inventory snapshot (`load_inventory`):
    sku_raw, sku, product_name, category, qty_on_hand, reorder_level,
    unit_cost, retail_price, last_count_date, location, notes

E-commerce orders (`load_ecommerce`):
    order_id, ecom_product_id, product_name, quantity, unit_price,
    total, order_date, status, customer_email, shipping_country
"""
from __future__ import annotations
from pathlib import Path
from typing import Union

import pandas as pd

from .config import ClientConfig, DEFAULT_CONFIG
from .normalize import normalize_sku, parse_flexible_date, clean_product_name


PathLike = Union[str, Path]


def load_pos(path: PathLike, cfg: ClientConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns={"sku": "sku_raw"})
    df["sku"] = df["sku_raw"].apply(lambda s: normalize_sku(s, cfg))
    df["product_name"] = df["product_name"].apply(clean_product_name)
    df["date"] = df["date"].apply(parse_flexible_date)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    return df


def load_inventory(path: PathLike, cfg: ClientConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    # Client-specific: this vendor puts data on 'Current Inventory' sheet.
    df = pd.read_excel(path, sheet_name="Current Inventory")
    # Client-specific column rename (part of the per-client config layer).
    df = df.rename(columns={
        "Item Code": "sku_raw",
        "Description": "product_name",
        "Category": "category",
        "Qty On Hand": "qty_on_hand",
        "Reorder Level": "reorder_level",
        "Unit Cost": "unit_cost",
        "Retail Price": "retail_price",
        "Last Count Date": "last_count_date",
        "Location": "location",
        "Notes": "notes",
    })
    df["sku"] = df["sku_raw"].apply(lambda s: normalize_sku(s, cfg))
    df["product_name"] = df["product_name"].apply(clean_product_name)
    df["last_count_date"] = df["last_count_date"].apply(parse_flexible_date)
    for c in ("qty_on_hand", "reorder_level", "unit_cost", "retail_price"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_ecommerce(path: PathLike) -> pd.DataFrame:
    import json
    with open(path) as f:
        payload = json.load(f)
    df = pd.DataFrame(payload["orders"])
    df = df.rename(columns={"product_id": "ecom_product_id"})
    df["product_name"] = df["product_name"].apply(clean_product_name)
    df["order_date"] = df["order_date"].apply(parse_flexible_date)
    for c in ("quantity", "unit_price", "total"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
