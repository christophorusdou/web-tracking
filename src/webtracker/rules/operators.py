"""Rule operators for condition evaluation."""

from __future__ import annotations

import re


def evaluate_operator(
    operator: str,
    current_value: str | None,
    expected_value: str | float | None,
    previous_value: str | None = None,
) -> bool:
    """Evaluate a single operator against current and previous values."""
    func = _OPERATORS.get(operator)
    if func is None:
        raise ValueError(f"Unknown operator: {operator}")
    return func(current_value, expected_value, previous_value)


def _equals(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    if current is None:
        return False
    return str(current) == str(expected)


def _not_equals(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    if current is None:
        return True
    return str(current) != str(expected)


def _contains(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    if current is None:
        return False
    return str(expected) in str(current)


def _not_contains(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    if current is None:
        return True
    return str(expected) not in str(current)


def _regex_match(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    if current is None:
        return False
    return bool(re.search(str(expected), str(current)))


def _less_than(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    try:
        return float(current) < float(expected)
    except (TypeError, ValueError):
        return False


def _greater_than(current: str | None, expected: str | float | None, _prev: str | None) -> bool:
    try:
        return float(current) > float(expected)
    except (TypeError, ValueError):
        return False


def _changed(current: str | None, _expected: str | float | None, prev: str | None) -> bool:
    if prev is None:
        return False  # no previous value = first run, don't alert
    return current != prev


def _appeared(current: str | None, _expected: str | float | None, prev: str | None) -> bool:
    return prev is None and current is not None


def _disappeared(current: str | None, _expected: str | float | None, prev: str | None) -> bool:
    return prev is not None and current is None


def _decreased_by_percent(
    current: str | None, expected: str | float | None, prev: str | None
) -> bool:
    try:
        cur = float(current)
        prv = float(prev)
        threshold = float(expected)
        if prv == 0:
            return False
        pct_decrease = ((prv - cur) / prv) * 100
        return pct_decrease >= threshold
    except (TypeError, ValueError):
        return False


def _increased_by_percent(
    current: str | None, expected: str | float | None, prev: str | None
) -> bool:
    try:
        cur = float(current)
        prv = float(prev)
        threshold = float(expected)
        if prv == 0:
            return False
        pct_increase = ((cur - prv) / prv) * 100
        return pct_increase >= threshold
    except (TypeError, ValueError):
        return False


def _exists(current: str | None, _expected: str | float | None, _prev: str | None) -> bool:
    return current is not None


def _not_exists(current: str | None, _expected: str | float | None, _prev: str | None) -> bool:
    return current is None


_OPERATORS: dict[str, callable] = {
    "equals": _equals,
    "not_equals": _not_equals,
    "contains": _contains,
    "not_contains": _not_contains,
    "regex_match": _regex_match,
    "less_than": _less_than,
    "greater_than": _greater_than,
    "changed": _changed,
    "appeared": _appeared,
    "disappeared": _disappeared,
    "decreased_by_percent": _decreased_by_percent,
    "increased_by_percent": _increased_by_percent,
    "exists": _exists,
    "not_exists": _not_exists,
}
