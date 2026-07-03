import math
from typing import Any


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.lower() == "nan"
    return False


def display_text(value: Any) -> str:
    return "" if is_blank(value) else str(value)


def optional_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    return str(value).strip() or None
