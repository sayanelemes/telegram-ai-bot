from typing import Union


def generate_progress_bar(current: Union[int, float], target: Union[int, float], length: int = 16) -> str:
    """Generate a visual text progress bar, e.g. ████████████░░░░ 66%."""
    if target <= 0:
        pct = 0.0
    else:
        pct = max(0.0, current / target)

    pct_int = int(round(pct * 100))
    filled_blocks = min(length, int(round(pct * length)))
    empty_blocks = max(0, length - filled_blocks)

    bar = "█" * filled_blocks + "░" * empty_blocks
    return f"{bar} {pct_int}%"


def format_number(val: Union[int, float]) -> str:
    """Format number with spaces as thousands separators (e.g. 1 450)."""
    if isinstance(val, float):
        if val.is_integer():
            val = int(val)
        else:
            formatted = f"{val:,.1f}".replace(",", " ")
            return formatted
    return f"{int(val):,}".replace(",", " ")


def format_currency(val: Union[int, float], currency: str = "₸") -> str:
    """Format currency amount (e.g. 8 450 ₸)."""
    return f"{format_number(val)} {currency}"
