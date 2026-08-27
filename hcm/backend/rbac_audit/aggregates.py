"""Shared small-cell suppression helpers for demographic aggregates.

Suppressing only the one small value is insufficient when an exact total,
percentage, or neighbouring value lets a caller reconstruct it. These helpers
hide every non-zero sibling in a related row once any sibling is small, and
withhold rates whose numerator is suppressed.
"""
from __future__ import annotations

SMALL_CELL_THRESHOLD = 5
SUPPRESSED_VALUE = f"<{SMALL_CELL_THRESHOLD}"


def suppress_count(value: int, *, suppress: bool) -> int | str:
    if suppress and 0 < value < SMALL_CELL_THRESHOLD:
        return SUPPRESSED_VALUE
    return value


def suppress_related_counts(
    counts: dict[str, int], *, suppress: bool
) -> tuple[dict[str, int | str], bool]:
    """Apply complementary suppression to one related set of counts."""
    has_small_cell = suppress and any(0 < value < SMALL_CELL_THRESHOLD for value in counts.values())
    if not has_small_cell:
        return dict(counts), False
    return {
        key: (SUPPRESSED_VALUE if 0 < value < SMALL_CELL_THRESHOLD else "Suppressed" if value > 0 else 0)
        for key, value in counts.items()
    }, True


def percentage(
    numerator: int, denominator: int, *, numerator_suppressed: bool, digits: int = 1
) -> float | None:
    if denominator == 0 or numerator_suppressed:
        return None
    return round(numerator / denominator * 100, digits)
