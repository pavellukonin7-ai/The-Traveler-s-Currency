"""Pure formatting and parsing helpers."""

from __future__ import annotations

import re


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def rate_text(value: float) -> str:
    if value >= 100:
        return f"{value:,.2f}".replace(",", " ")
    if value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.6f}".rstrip("0").rstrip(".")


def parse_amount(text: str) -> float | None:
    normalized = text.strip().replace(" ", "").replace(",", ".")
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    try:
        value = float(normalized)
    except ValueError:
        return None
    return value if 0 < value <= 1_000_000_000_000 else None


def progress_bar(spent: float, budget: float, width: int = 10) -> tuple[str, float]:
    percent = (spent / budget * 100) if budget > 0 else 0.0
    filled = min(width, max(0, round(percent / 100 * width)))
    return "▓" * filled + "░" * (width - filled), percent

