"""Identifier / value normalization helpers.

Every function here is deterministic and pure. These are the "reusable
bones" — they don't know anything about the specific client and make no
assumptions about downstream joins.
"""
from __future__ import annotations
import re
from datetime import datetime, date
from typing import Optional

import pandas as pd
from dateutil import parser as date_parser

from .config import ClientConfig, DEFAULT_CONFIG


_SKU_CLEAN = re.compile(r"[^A-Z0-9]")


def normalize_sku(raw, cfg: ClientConfig = DEFAULT_CONFIG) -> Optional[str]:
    """Canonical form of a SKU from any source.

    Handles: `SKU-50128`, `SKU50128`, `50128`, `050128`, `50128C` → `50128`.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    for p in cfg.sku_prefixes_to_strip:
        if s.startswith(p):
            s = s[len(p):]
    s = _SKU_CLEAN.sub("", s)
    if cfg.strip_trailing_variant_letter and len(s) > 1 and s[-1].isalpha() and s[:-1].isdigit():
        s = s[:-1]
    s = s.lstrip("0") or s  # keep at least one digit
    return s or None


def parse_flexible_date(raw) -> Optional[date]:
    """Parse dates across multiple formats (ISO, dd-mm-yyyy, mm/dd/yyyy, ...).

    Prefers ISO → day-first → month-first in that order to reduce ambiguity.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    # ISO first (unambiguous)
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    # dd-mm-yyyy
    if re.match(r"^\d{2}-\d{2}-\d{4}$", s):
        try:
            return datetime.strptime(s, "%d-%m-%Y").date()
        except ValueError:
            pass
    # mm/dd/yyyy (US)
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        try:
            return datetime.strptime(s, "%m/%d/%Y").date()
        except ValueError:
            pass
    # Last-resort parse, dayfirst=False so 11/18/2024 stays Nov 18
    try:
        return date_parser.parse(s, dayfirst=False).date()
    except (date_parser.ParserError, ValueError, TypeError):
        return None


def clean_product_name(raw) -> Optional[str]:
    """Normalize product name for fuzzy comparison. Case-fold, collapse whitespace."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = re.sub(r"\s+", " ", str(raw)).strip()
    return s.title() if s else None
