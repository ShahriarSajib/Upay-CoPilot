"""Synthetic financial dataset generation package."""

from __future__ import annotations

from .config import MONTHS, NUM_USERS, OUTPUT_DIR, SEED, SPLIT_DIRS, START_DATE
from .pipeline import build_dataset, generate_all

__all__ = [
    "MONTHS",
    "NUM_USERS",
    "OUTPUT_DIR",
    "SEED",
    "SPLIT_DIRS",
    "START_DATE",
    "build_dataset",
    "generate_all",
]