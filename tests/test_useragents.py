"""Tests for user-agent rotation."""

from webtracker.config import ExtractConfig, Operator, ConditionConfig, RuleConfig, TrackerConfig
from webtracker.engine.useragents import DEFAULT_USER_AGENTS, get_user_agent


def _make_tracker(**kwargs) -> TrackerConfig:
    """Helper to create a minimal TrackerConfig."""
    defaults = {
        "name": "Test",
        "url": "https://example.com",
        "extract": [ExtractConfig(name="x", selector="h1")],
        "rules": [RuleConfig(
            condition=ConditionConfig(field="x", operator=Operator.EXISTS),
            message="test",
        )],
    }
    defaults.update(kwargs)
    return TrackerConfig(**defaults)


class TestUserAgents:
    def test_default_pool_not_empty(self):
        assert len(DEFAULT_USER_AGENTS) >= 5

    def test_all_defaults_are_strings(self):
        for ua in DEFAULT_USER_AGENTS:
            assert isinstance(ua, str)
            assert "Mozilla" in ua

    def test_returns_from_default_pool(self):
        tracker = _make_tracker()
        ua = get_user_agent(tracker)
        assert ua in DEFAULT_USER_AGENTS

    def test_returns_from_custom_pool(self):
        custom = ["CustomBot/1.0", "CustomBot/2.0"]
        tracker = _make_tracker(user_agents=custom)
        ua = get_user_agent(tracker)
        assert ua in custom

    def test_rotation_produces_variety(self):
        """Over 50 calls, we should see more than 1 distinct UA."""
        tracker = _make_tracker()
        seen = {get_user_agent(tracker) for _ in range(50)}
        assert len(seen) > 1
