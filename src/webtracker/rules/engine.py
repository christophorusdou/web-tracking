"""Rule evaluation engine."""

from __future__ import annotations

from webtracker.config import ConditionConfig, Operator, RuleConfig
from webtracker.rules.operators import compute_percent_change, evaluate_operator


def evaluate_rules(
    rules: list[RuleConfig],
    current_values: dict[str, str | None],
    previous_values: dict[str, str | None],
) -> list[tuple[int, RuleConfig, str]]:
    """Evaluate all rules against current and previous values.

    Returns list of (rule_index, rule, formatted_message) for triggered rules.
    """
    triggered: list[tuple[int, RuleConfig, str]] = []

    for idx, rule in enumerate(rules):
        if _evaluate_condition(rule.condition, current_values, previous_values):
            message = _format_message(rule.message, current_values, previous_values)
            triggered.append((idx, rule, message))

    return triggered


def _evaluate_condition(
    condition: ConditionConfig,
    current_values: dict[str, str | None],
    previous_values: dict[str, str | None],
) -> bool:
    """Recursively evaluate a condition tree."""
    if condition.operator == Operator.AND:
        return all(
            _evaluate_condition(c, current_values, previous_values)
            for c in condition.conditions
        )
    if condition.operator == Operator.OR:
        return any(
            _evaluate_condition(c, current_values, previous_values)
            for c in condition.conditions
        )

    current = current_values.get(condition.field)
    previous = previous_values.get(condition.field)

    return evaluate_operator(
        condition.operator,
        current,
        condition.value,
        previous,
    )


def _format_message(
    template: str,
    current_values: dict[str, str | None],
    previous_values: dict[str, str | None],
) -> str:
    """Format a message template with extracted values.

    Supports ${field_name} for current values and ${prev_field_name} for previous.
    Also computes ${change_percent} for numeric comparisons.
    """
    result = template

    # Replace ${field} with current values
    for field, value in current_values.items():
        result = result.replace(f"${{{field}}}", str(value) if value is not None else "N/A")

    # Replace ${prev_field} with previous values
    for field, value in previous_values.items():
        result = result.replace(f"${{prev_{field}}}", str(value) if value is not None else "N/A")

    # Compute ${change_percent} only if the placeholder is present
    if "${change_percent}" in result:
        for field in current_values:
            pct = compute_percent_change(current_values.get(field), previous_values.get(field))
            if pct is not None:
                result = result.replace("${change_percent}", f"{abs(pct):.1f}")
                break
        else:
            result = result.replace("${change_percent}", "?")

    return result
