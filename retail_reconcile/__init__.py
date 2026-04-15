"""Reusable retail-data reconciliation toolkit.

Scope: cleaning, identifier normalization, cross-source joining, and inventory
health analytics. Client-specific mappings live in `config.py`; everything
else is intended to be reusable for the next retail engagement.
"""
from .loaders import load_pos, load_inventory, load_ecommerce
from .normalize import normalize_sku, parse_flexible_date, clean_product_name
from .reconcile import build_product_master, reconcile_sources
from .insights import (
    stockout_risk,
    dead_inventory,
    reconciliation_gaps,
    channel_performance,
    data_quality_report,
)
