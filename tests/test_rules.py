"""Tests for the rule engine and operators."""

import pytest

from webtracker.config import ConditionConfig, Operator, RuleConfig
from webtracker.rules.engine import evaluate_rules
from webtracker.rules.operators import evaluate_operator


class TestOperators:
    def test_equals(self):
        assert evaluate_operator(Operator.EQUALS, "hello", "hello") is True
        assert evaluate_operator(Operator.EQUALS, "hello", "world") is False
        assert evaluate_operator(Operator.EQUALS, None, "hello") is False

    def test_not_equals(self):
        assert evaluate_operator(Operator.NOT_EQUALS, "hello", "world") is True
        assert evaluate_operator(Operator.NOT_EQUALS, "hello", "hello") is False

    def test_contains(self):
        assert evaluate_operator(Operator.CONTAINS, "Add to Cart", "Add to Cart") is True
        assert evaluate_operator(Operator.CONTAINS, "Add to Cart - PS5", "Add to Cart") is True
        assert evaluate_operator(Operator.CONTAINS, "Sold Out", "Add to Cart") is False

    def test_not_contains(self):
        assert evaluate_operator(Operator.NOT_CONTAINS, "Sold Out", "Add to Cart") is True
        assert evaluate_operator(Operator.NOT_CONTAINS, "Add to Cart", "Add to Cart") is False

    def test_less_than(self):
        assert evaluate_operator(Operator.LESS_THAN, "99.99", 100) is True
        assert evaluate_operator(Operator.LESS_THAN, "150", 100) is False
        assert evaluate_operator(Operator.LESS_THAN, "invalid", 100) is False

    def test_greater_than(self):
        assert evaluate_operator(Operator.GREATER_THAN, "150", 100) is True
        assert evaluate_operator(Operator.GREATER_THAN, "50", 100) is False

    def test_changed(self):
        assert evaluate_operator(Operator.CHANGED, "new", None, "old") is True
        assert evaluate_operator(Operator.CHANGED, "same", None, "same") is False
        assert evaluate_operator(Operator.CHANGED, "value", None, None) is False  # first run

    def test_appeared(self):
        assert evaluate_operator(Operator.APPEARED, "hello", None, None) is True
        assert evaluate_operator(Operator.APPEARED, "hello", None, "prev") is False

    def test_disappeared(self):
        assert evaluate_operator(Operator.DISAPPEARED, None, None, "was_here") is True
        assert evaluate_operator(Operator.DISAPPEARED, "still_here", None, "was_here") is False

    def test_decreased_by_percent(self):
        assert evaluate_operator(Operator.DECREASED_BY_PERCENT, "90", 10, "100") is True  # 10% drop
        assert evaluate_operator(Operator.DECREASED_BY_PERCENT, "95", 10, "100") is False  # only 5%
        assert evaluate_operator(Operator.DECREASED_BY_PERCENT, "invalid", 10, "100") is False

    def test_increased_by_percent(self):
        assert evaluate_operator(Operator.INCREASED_BY_PERCENT, "120", 10, "100") is True  # 20% up
        assert evaluate_operator(Operator.INCREASED_BY_PERCENT, "105", 10, "100") is False  # only 5%

    def test_exists(self):
        assert evaluate_operator(Operator.EXISTS, "value", None) is True
        assert evaluate_operator(Operator.EXISTS, None, None) is False

    def test_not_exists(self):
        assert evaluate_operator(Operator.NOT_EXISTS, None, None) is True
        assert evaluate_operator(Operator.NOT_EXISTS, "value", None) is False


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
