import re

_MEAL_TIME_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")


def normalize_meal_time(value: object) -> str | None:
    """Normalize a meal time to HH:MM, returning None for blank or invalid input."""
    text = str(value or "").strip()
    match = _MEAL_TIME_PATTERN.fullmatch(text)
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def require_meal_time(value: object) -> str:
    normalized = normalize_meal_time(value)
    if normalized is None:
        raise ValueError("用餐时间必须是 HH:MM 格式")
    return normalized


def infer_meal_type(value: object) -> str | None:
    """Infer only conventional meal windows; ambiguous times remain unlabeled."""
    normalized = normalize_meal_time(value)
    if normalized is None:
        return None

    hour, minute = (int(part) for part in normalized.split(":"))
    minutes = hour * 60 + minute
    if 5 * 60 <= minutes < 10 * 60:
        return "早餐"
    if 11 * 60 <= minutes < 14 * 60:
        return "午餐"
    if 17 * 60 <= minutes < 21 * 60:
        return "晚餐"
    return None


def resolve_meal_type(explicit_label: object, meal_time: object) -> str | None:
    label = str(explicit_label or "").strip()
    return label or infer_meal_type(meal_time)
