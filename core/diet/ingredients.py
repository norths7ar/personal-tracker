import re

from core.text import display_text

INGREDIENT_SEPARATOR_PATTERN = re.compile(r"[、,，;；\n]+")


def normalize_ingredients(value) -> list[str]:
    """Return unique, nonblank ingredient names while preserving order."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    normalized = []
    seen = set()
    for item in values:
        for part in INGREDIENT_SEPARATOR_PATTERN.split(display_text(item)):
            name = part.strip()
            if name and name not in seen:
                seen.add(name)
                normalized.append(name)
    return normalized
