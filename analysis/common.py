"""Shared paths and loaders. Tables come from the private repo (built by its scripts/tables.py), never from here.

Locally `private/` is a symlink to a clone of Tolar-dio/nba-private; in the nightly it's a checkout with a read-only
token. NBA_TABLES overrides the location.
"""
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.environ.get("NBA_TABLES") or os.path.join(ROOT, "private", "bdl", "tables")
OUT = os.path.join(ROOT, "analysis", "output")
PREV, CUR = 2025, 2026          # BDL season labels: 2025 = 2025-26, 2026 = 2026-27


def table(season, name):
    return pd.read_csv(os.path.join(TABLES, str(season), f"{name}.csv.gz"))


def out_path(season, name):
    d = os.path.join(OUT, str(season))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def logloss(y, p, eps=1e-6):
    import numpy as np
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
