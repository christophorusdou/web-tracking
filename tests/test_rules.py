"""Tests for the rule engine and operators."""

import pytest

from webtracker.config import ConditionConfig, Operator, RuleConfig
from webtracker.rules.engine import evaluate_rules
from webtracker.rules.operators import evaluate_operator


class TestOperators:
    def test_equals(self):
        assert evaluate_operator("equals", "hello", "hello") is True
        assert evaluate_operator("equals", "hello", "world") is False
        assert evaluate_operator("equals", None, "hello") is False

    def test_not_equals(self):
        assert evaluate_operator("not_equals", "hello", "world") is True
        assert evaluate_operator("not_equals", "hello", "hello") is False

    def test_contains(self):
        assert evaluate_operator("contains", "Add to Cart", "Add to Cart") is True
        assert evaluate_operator("contains", "Add to Cart - PS5", "Add to Cart") is True
        assert evaluate_operator("contains", "Sold Out", "Add to Cart") is False

    def test_not_contains(self):
        assert evaluate_operator("not_contains", "Sold Out", "Add to Cart") is True
        assert evaluate_operator("not_contains", "Add to Cart", "Add to Cart") is False

    def test_less_than(self):
        assert evaluate_operator("less_than", "99.99", 100) is True
        assert evaluate_operator("less_than", "150", 100) is False
        assert evaluate_operator("less_than", "invalid", 100) is False

    def test_greater_than(self):
        assert evaluate_operator("greater_than", "150", 100) is True
        assert evaluate_operator("greater_than", "50", 100) is False

    def test_changed(self):
        assert evaluate_operator("changed", "new", None, "old") is True
        assert evaluate_operator("changed", "same", None, "same") is False
        assert evaluate_operator("changed", "value", None, None) is False  # first run

    def test_appeared(self):
        assert evaluate_operator("appeared", "hello", None, None) is True
        assert evaluate_operator("appeared", "hello", None, "prev") is False

    def test_disappeared(self):
        assert evaluate_operator("disappeared", None, None, "was_here") is True
        assert evaluate_operator("disappeared", "still_here", None, "was_here") is False

    def test_decreased_by_percent(self):
        assert evaluate_operator("decreased_by_percent", "90", 10, "100") is True  # 10% drop
        assert evaluate_operator("decreased_by_percent", "95", 10, "100") is False  # only 5%
        assert evaluate_operator("decreased_by_percent", "invalid", 10, "100") is False

    def test_increased_by_percent(self):
        assert evaluate_operator("increased_by_percent", "120", 10, "100") is True  # 20% up
        assert evaluate_operator("increased_by_percent", "105", 10, "100") is False  # only 5%

    def test_exists(self):
        assert evaluate_operator("exists", "value", None) is True
        assert evaluate_operator("exists", None, None) is False

    def test_not_exists(self):
        assert evaluate_operator("not_exists", None, None) is True
        assert evaluate_operator("not_exists", "value", None) is False


class TestRuleEngine:
    def test_simple_rule_triggers(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(
                    field="price",
                    operator=Operator.LESS_THAN,
                    value=100,
                ),
                message="Price dropped to $${price}!",
            )
        ]
        triggered = evaluate_rules(rules, {"price": "79.99"}, {})
        assert len(triggered) == 1
        assert "$79.99" in triggered[0][2]

    def test_simple_rule_does_not_trigger(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(
                    field="price",
                    operator=Operator.LESS_THAN,
                    value=100,
                ),
                message="Price dropped!",
            )
        ]
        triggered = evaluate_rules(rules, {"price": "150"}, {})
        assert len(triggered) == 0

    def test_changed_rule(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(
                    field="content_hash",
                    operator=Operator.CHANGED,
                ),
                message="Content changed!",
            )
        ]
        # First run: no previous value → should NOT trigger
        triggered = evaluate_rules(rules, {"content_hash": "abc123"}, {})
        assert len(triggered) == 0

        # Subsequent run with different value → should trigger
        triggered = evaluate_rules(rules, {"content_hash": "def456"}, {"content_hash": "abc123"})
        assert len(triggered) == 1

    def test_and_condition(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(
                    operator=Operator.AND,
                    conditions=[
                        ConditionConfig(field="price", operator=Operator.LESS_THAN, value=300),
                        ConditionConfig(field="stock", operator=Operator.CONTAINS, value="In Stock"),
                    ],
                ),
                message="Good deal!",
            )
        ]
        # Both true
        triggered = evaluate_rules(rules, {"price": "250", "stock": "In Stock"}, {})
        assert len(triggered) == 1

        # Price too high
        triggered = evaluate_rules(rules, {"price": "350", "stock": "In Stock"}, {})
        assert len(triggered) == 0

    def test_or_condition(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(
                    operator=Operator.OR,
                    conditions=[
                        ConditionConfig(field="status", operator=Operator.CONTAINS, value="In Stock"),
                        ConditionConfig(field="status", operator=Operator.CONTAINS, value="Available"),
                    ],
                ),
                message="Item available!",
            )
        ]
        triggered = evaluate_rules(rules, {"status": "Available Now"}, {})
        assert len(triggered) == 1

        triggered = evaluate_rules(rules, {"status": "Sold Out"}, {})
        assert len(triggered) == 0

    def test_message_formatting(self):
        rules = [
            RuleConfig(
                condition=ConditionConfig(field="price", operator=Operator.LESS_THAN, value=100),
                message="Product: ${title} at $${price}",
            )
        ]
        triggered = evaluate_rules(rules, {"price": "79.99", "title": "Widget"}, {})
        assert triggered[0][2] == "Product: Widget at $79.99"
