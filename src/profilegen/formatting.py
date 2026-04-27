"""Pure text formatting utilities with no internal dependencies."""

import datetime
import time
from typing import Any

from dateutil import relativedelta


def format_age(birthday: datetime.datetime) -> str:
    """Format the age difference between today and a birthday as a human-readable string.

    Args:
        birthday: The date of birth.

    Returns:
        A string like ``"38 years, 2 months, 22 days"`` with a cake emoji on the
        exact birthday.
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    parts = [
        f"{diff.years} year{_plural(diff.years)}",
        f"{diff.months} month{_plural(diff.months)}",
        f"{diff.days} day{_plural(diff.days)}",
    ]
    suffix = " 🎂" if diff.months == 0 and diff.days == 0 else ""
    return ", ".join(parts) + suffix


def _plural(value: int) -> str:
    """Return ``'s'`` when *value* is not 1."""
    return "s" if value != 1 else ""


def format_compact_number(value: int | str) -> str:
    """Format a number into a compact representation (e.g. ``1.2K``, ``3.45M``).

    Args:
        value: An integer or a string that may already contain a ``K``/``M`` suffix.

    Returns:
        A compact string representation of the number.
    """
    if isinstance(value, str):
        normalized = value.replace(",", "").strip().upper()
        if normalized.endswith(("M", "K")):
            return value
        value = int(normalized)

    absolute_value = abs(value)
    if absolute_value >= 1_000_000:
        formatted = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}M"
    if absolute_value >= 1_000:
        formatted = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{formatted}K"
    return str(value)


def format_display_text(value: int | str) -> str:
    """Format a value for display, adding thousands separators to integers.

    Args:
        value: An integer or string value to format.

    Returns:
        The formatted string.
    """
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def perf_counter(function: Any, *args: Any) -> tuple[Any, float]:
    """Time the execution of *function* and return its result with the elapsed time.

    Args:
        function: The callable to time.
        *args: Positional arguments forwarded to *function*.

    Returns:
        A tuple of ``(result, elapsed_seconds)``.
    """
    start = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter() - start


def print_duration(label: str, duration: float) -> None:
    """Print a timing label and duration in seconds or milliseconds.

    Args:
        label: A short description of the timed operation.
        duration: Elapsed time in seconds.
    """
    metric = f"{duration:.4f} s" if duration > 1 else f"{duration * 1000:.4f} ms"
    print(f"   {label + ':':<20}{metric:>12}")
