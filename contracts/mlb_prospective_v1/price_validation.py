"""Decision-time sportsbook price validation for prospective MLB capture.

Reuses Phase 0 evidence-contract Principle 7 verbatim: DFS placeholder
prices are not sportsbook prices. No DFS placeholder price may become
sportsbook evidence in a prospective decision either.
"""
from typing import Optional

DFS_PLACEHOLDER_BOOK_MARKERS = frozenset(
    {
        "dfs_placeholder",
        "prizepicks",
        "underdog_fantasy_placeholder",
        "internal_dfs_reference",
    }
)

MIN_PLAUSIBLE_AMERICAN_ODDS = 100
MAX_PLAUSIBLE_AMERICAN_ODDS = 100000


def is_dfs_placeholder_book(book: Optional[str]) -> bool:
    if not book:
        return False
    return book.strip().lower() in DFS_PLACEHOLDER_BOOK_MARKERS


def is_valid_sportsbook_price(odds_american: Optional[int], book: Optional[str]) -> bool:
    if odds_american is None or odds_american == 0:
        return False
    if is_dfs_placeholder_book(book):
        return False
    magnitude = abs(int(odds_american))
    return MIN_PLAUSIBLE_AMERICAN_ODDS <= magnitude <= MAX_PLAUSIBLE_AMERICAN_ODDS
