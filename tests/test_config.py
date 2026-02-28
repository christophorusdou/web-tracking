"""Tests for configuration loading and validation."""

import textwrap
from pathlib import Path

import pytest
import yaml

from webtracker.config import (
    AppConfig,
    ConditionConfig,
    EngineType,
    NotifyChannelType,
    Operator,
    load_config,
)


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    config = {
        "settings": {
            "state_db": str(tmp_path / "state.db"),
            "log_level": "debug",
        },
        "notifications": {
            "channels": {
                "test_ntfy": {
                    "type": "ntfy",
                    "topic": "test-topic",
                }
            },
            "defaults": {
                "channels": ["test_ntfy"],
                "cooldown": 60,
            },
        },
        "trackers": {
            "test_tracker": {
                "name": "Test Tracker",
                "engine": "http",
                "url": "https://example.com",
                "schedule": {"interval": 300},
                "extract": [
                    {
                        "name": "title",
                        "selector": "h1",
                        "attribute": "text",
                        "transform": ["strip"],
                    }
                ],
                "rules": [
                    {
                        "condition": {
                            "field": "title",
                            "operator": "changed",
                        },
                        "message": "Title changed to: ${title}",
                    }
                ],
            }
        },
    }
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


def test_load_valid_config(sample_config_path: Path):
    config = load_config(sample_config_path)
    assert isinstance(config, AppConfig)
    assert "test_tracker" in config.trackers
    assert config.trackers["test_tracker"].engine == EngineType.HTTP
    assert config.trackers["test_tracker"].name == "Test Tracker"
    assert len(config.trackers["test_tracker"].extract) == 1
    assert len(config.trackers["test_tracker"].rules) == 1


def test_config_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_notification_channel_types(sample_config_path: Path):
    config = load_config(sample_config_path)
    channel = config.notifications.channels["test_ntfy"]
    assert channel.type == NotifyChannelType.NTFY


def test_and_condition():
    cond = ConditionConfig(
        operator=Operator.AND,
        conditions=[
            ConditionConfig(field="price", operator=Operator.LESS_THAN, value=100),
            ConditionConfig(field="stock", operator=Operator.CONTAINS, value="In Stock"),
        ],
    )
    assert cond.operator == Operator.AND
    assert len(cond.conditions) == 2


def test_and_condition_requires_conditions():
    with pytest.raises(Exception):
        ConditionConfig(operator=Operator.AND)


def test_simple_condition_requires_field():
    with pytest.raises(Exception):
        ConditionConfig(operator=Operator.EQUALS, value="test")
