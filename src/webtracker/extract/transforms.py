"""Transform functions for extracted values."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

_TRANSFORM_PATTERN = re.compile(r"(\w+)\((.+)\)")


def apply_transforms(value: str | None, transforms: list[str]) -> str | None:
    """Apply a chain of transforms to an extracted value."""
    if value is None:
        return None
    for transform in transforms:
        value = _apply_single(value, transform)
        if value is None:
            return None
    return value


def _apply_single(value: str, transform: str) -> str | None:
    """Apply a single transform."""
    # Handle parameterized transforms like regex_extract("pattern")
    match = _TRANSFORM_PATTERN.match(transform)
    if match:
        func_name = match.group(1)
        param = match.group(2).strip("\"'")
        func = _PARAMETERIZED_TRANSFORMS.get(func_name)
        if func is None:
            raise ValueError(
                f"Unknown parameterized transform: '{func_name}'. "
                f"Available: {', '.join(_PARAMETERIZED_TRANSFORMS)}"
            )
        return func(value, param)

    func = _SIMPLE_TRANSFORMS.get(transform)
    if func is None:
        raise ValueError(
            f"Unknown transform: '{transform}'. "
            f"Available: {', '.join(_SIMPLE_TRANSFORMS)}"
        )
    return func(value)


def _strip(value: str) -> str:
    return value.strip()


def _lowercase(value: str) -> str:
    return value.lower()


def _uppercase(value: str) -> str:
    return value.upper()


def _to_number(value: str) -> str:
    """Extract numeric value, removing currency symbols and commas."""
    cleaned = re.sub(r"[^\d.\-]", "", value)
    if not cleaned:
        return value
    return cleaned


def _hash_md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _first_line(value: str) -> str:
    return value.split("\n")[0]


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _regex_extract(value: str, pattern: str) -> str | None:
    m = re.search(pattern, value)
    if m:
        return m.group(1) if m.groups() else m.group(0)
    return None


def _truncate(value: str, length: str) -> str:
    return value[: int(length)]


_SIMPLE_TRANSFORMS: dict[str, Callable[[str], str | None]] = {
    "strip": _strip,
    "lowercase": _lowercase,
    "uppercase": _uppercase,
    "to_number": _to_number,
    "hash_md5": _hash_md5,
    "first_line": _first_line,
    "collapse_whitespace": _collapse_whitespace,
}

_PARAMETERIZED_TRANSFORMS: dict[str, Callable[[str, str], str | None]] = {
    "regex_extract": _regex_extract,
    "truncate": _truncate,
}
