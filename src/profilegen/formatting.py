"""Pure text formatting utilities with no internal dependencies."""

import datetime
import time

from dateutil import relativedelta


def format_age(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    parts = [
        f"{diff.years} year{_plural(diff.years)}",
        f"{diff.months} month{_plural(diff.months)}",
        f"{diff.days} day{_plural(diff.days)}",
    ]
    suffix = " 🎂" if diff.months == 0 and diff.days == 0 else ""
    return ", ".join(parts) + suffix


def _plural(value):
    return "s" if value != 1 else ""


def format_compact_number(value):
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


def format_display_text(value):
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def perf_counter(function, *args):
    start = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter() - start


def print_duration(label, duration):
    metric = f"{duration:.4f} s" if duration > 1 else f"{duration * 1000:.4f} ms"
    print(f"   {label + ':':<20}{metric:>12}")
