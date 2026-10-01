"""Display-only terminology. Never use these strings as control identifiers."""
import re


def display_text(value):
    text = str(value)
    for old, new in (
        ("Hybrid Grid Hold", "Grid Hold"),
        ("Panic Grid Hold", "Reserve Hold"),
        ("Adaptive Hybrid", "Low-Tariff Plan"),
        ("Hybrid", "Low-Tariff"),
        ("Panic", "Reserve Protection"),
        ("AHM", "Battery Reserve"),
        ("Grid Confidence", "Grid Reliability"),
    ):
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
    return text


def display_value(key, value):
    # Raw enum states, sensor keys and command values remain unchanged.
    if key.endswith(("_reason", "_target_source", "_calculation")):
        return display_text(value)
    return str(value)
