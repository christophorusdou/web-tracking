"""YAML configuration loader and Pydantic models."""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────


class EngineType(str, Enum):
    HTTP = "http"
    BROWSER = "browser"


class AuthType(str, Enum):
    COOKIES = "cookies"
    BROWSER_PROFILE = "browser_profile"


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    REGEX_MATCH = "regex_match"
    LESS_THAN = "less_than"
    GREATER_THAN = "greater_than"
    CHANGED = "changed"
    APPEARED = "appeared"
    DISAPPEARED = "disappeared"
    DECREASED_BY_PERCENT = "decreased_by_percent"
    INCREASED_BY_PERCENT = "increased_by_percent"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    AND = "and"
    OR = "or"


class NotifyChannelType(str, Enum):
    NTFY = "ntfy"
    PUSHOVER = "pushover"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"


class ActionType(str, Enum):
    CLICK = "click"
    SCROLL = "scroll"
    WAIT = "wait"
    TYPE = "type"


# ── Notification Channel Configs ─────────────────────────


class NtfyConfig(BaseModel):
    type: NotifyChannelType = NotifyChannelType.NTFY
    server: str = "https://ntfy.sh"
    topic: str
    priority: str = "default"


class PushoverConfig(BaseModel):
    type: NotifyChannelType = NotifyChannelType.PUSHOVER
    user_key: str
    api_token: str
    priority: int = 0
    sound: str = "pushover"


class TelegramConfig(BaseModel):
    type: NotifyChannelType = NotifyChannelType.TELEGRAM
    bot_token: str
    chat_id: str


class EmailConfig(BaseModel):
    type: NotifyChannelType = NotifyChannelType.EMAIL
    smtp_host: str
    smtp_port: int = 587
    username: str
    password: str
    from_addr: str = Field(alias="from")
    to: str


class WebhookConfig(BaseModel):
    type: NotifyChannelType = NotifyChannelType.WEBHOOK
    url: str
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)


ChannelConfig = NtfyConfig | PushoverConfig | TelegramConfig | EmailConfig | WebhookConfig


def _parse_channel(data: dict[str, Any]) -> ChannelConfig:
    """Parse a channel config dict into the correct typed model."""
    type_map: dict[str, type[ChannelConfig]] = {
        "ntfy": NtfyConfig,
        "pushover": PushoverConfig,
        "telegram": TelegramConfig,
        "email": EmailConfig,
        "webhook": WebhookConfig,
    }
    channel_type = data.get("type", "")
    cls = type_map.get(channel_type)
    if cls is None:
        raise ValueError(f"Unknown notification channel type: {channel_type}")
    return cls(**data)


# ── Notification Settings ────────────────────────────────


class NotificationDefaults(BaseModel):
    channels: list[str] = Field(default_factory=lambda: ["ntfy_phone"])
    cooldown: int = Field(default=300, ge=0)
    on_error_notify: bool = True
    error_threshold: int = Field(default=3, ge=1)


class NotificationSettings(BaseModel):
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    defaults: NotificationDefaults = Field(default_factory=NotificationDefaults)

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, v: dict[str, Any]) -> dict[str, ChannelConfig]:
        return {name: _parse_channel(cfg) for name, cfg in v.items()}


# ── Browser Settings ────────────────────────────────────


class BrowserSettings(BaseModel):
    headless: bool = True
    user_data_dir: str = "./browser_profiles/default"
    default_timeout: int = 30000


class GlobalSettings(BaseModel):
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    state_db: str = "./data/state.db"
    log_level: str = "info"


# ── Tracker Models ───────────────────────────────────────


class AuthConfig(BaseModel):
    type: AuthType
    file: str | None = None
    profile: str | None = None

    @model_validator(mode="after")
    def validate_auth(self) -> AuthConfig:
        if self.type == AuthType.COOKIES and not self.file:
            raise ValueError("Cookie auth requires 'file' path")
        if self.type == AuthType.BROWSER_PROFILE and not self.profile:
            raise ValueError("Browser profile auth requires 'profile' name")
        return self


class ScheduleConfig(BaseModel):
    interval: int = Field(default=300, ge=10)  # seconds, minimum 10s
    jitter: int = Field(default=0, ge=0)
    active_hours: str | None = None  # e.g. "07:00-21:00"
    retry_count: int = Field(default=0, ge=0, le=10)  # max retries on fetch failure
    retry_delay: int = Field(default=5, ge=1, le=300)  # initial backoff in seconds

    @field_validator("active_hours")
    @classmethod
    def validate_active_hours(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", v):
            raise ValueError("active_hours must be in format 'HH:MM-HH:MM'")
        return v


class ExtractConfig(BaseModel):
    name: str
    selector: str
    attribute: str = "text"
    transform: list[str] = Field(default_factory=list)


class ConditionConfig(BaseModel):
    field: str | None = None
    operator: Operator
    value: Any = None
    conditions: list[ConditionConfig] | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> ConditionConfig:
        if self.operator in (Operator.AND, Operator.OR):
            if not self.conditions:
                raise ValueError(f"'{self.operator.value}' requires 'conditions' list")
        else:
            if self.field is None:
                raise ValueError(f"'{self.operator.value}' requires 'field'")
        return self


class RuleConfig(BaseModel):
    condition: ConditionConfig
    message: str
    channels: list[str] | None = None
    priority: str | None = None


class PageAction(BaseModel):
    type: ActionType
    selector: str | None = None
    amount: int | None = None
    text: str | None = None
    timeout: int | None = None


class WaitForConfig(BaseModel):
    selector: str
    timeout: int = 10000


class TrackerConfig(BaseModel):
    name: str
    engine: EngineType = EngineType.HTTP
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    proxy: str | None = None
    user_agents: list[str] = Field(default_factory=list)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    auth: AuthConfig | None = None
    wait_for: WaitForConfig | None = None
    actions: list[PageAction] = Field(default_factory=list)
    extract: list[ExtractConfig]
    rules: list[RuleConfig]


# ── Top-Level Config ─────────────────────────────────────


class AppConfig(BaseModel):
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    trackers: dict[str, TrackerConfig] = Field(default_factory=dict)


# ── Loader ───────────────────────────────────────────────

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)}")


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(obj, str):
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return _ENV_VAR_PATTERN.sub(replacer, obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def load_config(path: str | Path) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError("Config file is empty")

    resolved = _resolve_env_vars(raw)
    return AppConfig(**resolved)
