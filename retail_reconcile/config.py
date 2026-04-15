"""Client-specific configuration.

This is the file that changes per client. Everything else in the package
should work unchanged against any retail dataset that can be coerced into
the canonical schemas documented in `loaders.py`.
"""
from dataclasses import dataclass, field


@dataclass
class ClientConfig:
    # SKU prefixes we strip during normalization. POS vendors love to invent these.
    sku_prefixes_to_strip: tuple = ("SKU-", "SKU")
    # If a POS SKU has a trailing single letter (e.g. 61613C), treat it as
    # the same item — the letter is usually a size/variant marker the POS
    # operator tacked on. Toggle off for clients that use real variant codes.
    strip_trailing_variant_letter: bool = True
    # Priority ordering for quantity-on-hand conflicts between sources.
    # Ops-team manual overrides (Notes column) beat everything.
    quantity_source_priority: tuple = ("notes_override", "inventory_system", "ecommerce", "pos_derived")
    # Number of days with zero sales before an SKU is flagged as dead.
    dead_inventory_days: int = 60
    # Days of forward cover below which we flag stockout risk.
    stockout_days_cover_threshold: int = 14
    # For fuzzy product-name matching between POS/Inventory and E-commerce.
    fuzzy_match_threshold: int = 88  # 0-100, rapidfuzz token_sort_ratio


DEFAULT_CONFIG = ClientConfig()
