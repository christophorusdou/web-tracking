"""Rule operators for condition evaluation."""

from __future__ import annotations

import re
from collections.abc import Callable

from webtracker.config import Operator

# Type alias for operator functions
OperatorFunc = Callable[[str | None, str | float | None, str | None], bool]


def evaluate_operator(
    operator: Operator,
    current_value: str | None,
    expected_value: str | float | None,
    previous_value: str | None = None,
) -> bool:
    """Evaluate a single operator against current and previous values."""
    func = _OPERATORS.get(operator)
    if func is None:
        raise ValueError(f"Unknown operator: {operator}")
    return func(current_value, expected_value, previous_value)


def compute_percent_change(current: str | None, previous: str | None) -> float | None:
    """Compute the signed percentage change from previous to current.

    Returns positive for increases, negative for decreases, or None if not computable.
    """
    try:
        cur = float(current)
        prv = float(previous)
        if prv == 0:
            return None
        return ((cur - prv) / prv) * 100
    except (TypeError, ValueError):
        return None


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
    pct = compute_percent_change(current, prev)
    if pct is None:
        return False
    try:
        return -pct >= float(expected)
    except (TypeError, ValueError):
        return False


def _increased_by_percent(
    current: str | None, expected: str | float | None, prev: str | None
) -> bool:
    pct = compute_percent_change(current, prev)
    if pct is None:
        return False
    try:
        return pct >= float(expected)
    except (TypeError, ValueError):
        return False


def _exists(current: str | None, _expected: str | float | None, _prev: str | None) -> bool:
    return current is not None


def _not_exists(current: str | None, _expected: str | float | None, _prev: str | None) -> bool:
    return current is None


_OPERATORS: dict[Operator, OperatorFunc] = {
    Operator.EQUALS: _equals,
    Operator.NOT_EQUALS: _not_equals,
    Operator.CONTAINS: _contains,
    Operator.NOT_CONTAINS: _not_contains,
    Operator.REGEX_MATCH: _regex_match,
    Operator.LESS_THAN: _less_than,
    Operator.GREATER_THAN: _greater_than,
    Operator.CHANGED: _changed,
    Operator.APPEARED: _appeared,
    Operator.DISAPPEARED: _disappeared,
    Operator.DECREASED_BY_PERCENT: _decreased_by_percent,
    Operator.INCREASED_BY_PERCENT: _increased_by_percent,
    Operator.EXISTS: _exists,
    Operator.NOT_EXISTS: _not_exists,
}
