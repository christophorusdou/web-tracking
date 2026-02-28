# WebTracker

A flexible, config-driven system that monitors web pages for specific conditions and sends instant notifications through multiple channels. Track anything — stock availability, price drops, new posts, content changes — without writing code.

## Features

- **Dual engine architecture** — lightweight HTTP (httpx) for simple pages, full browser (Playwright) for JS-heavy sites
- **Declarative rules** — define what to watch and when to alert using YAML, no code required
- **14 condition operators** — equals, contains, regex_match, less_than, changed, appeared, decreased_by_percent, and more
- **5 notification channels** — Ntfy.sh, Pushover, Telegram, Email (SMTP), generic Webhook
- **Anti-detection** — user-agent rotation, per-tracker proxy support, request jitter, active hours
- **Retry with backoff** — automatic exponential backoff on transient failures
- **Web dashboard** — real-time status page with tracker health, values, and notification history
- **Browser profile auth** — log in once manually, reuse the session forever
- **SQLite state store** — tracks values over time, enforces notification cooldowns, records error history

## Quick Start

```bash
# Install
pip install -e ".[dashboard]"
playwright install chromium

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your trackers and notification channels

# Validate config
webtracker config validate

# Test a single tracker
webtracker test my_tracker

# Run all trackers
webtracker run

# Start the dashboard
webtracker dashboard
```

See [SETUP.md](SETUP.md) for detailed installation and configuration instructions.

## How It Works

```
YAML Config → Scheduler → Engine (HTTP/Browser) → Extract (CSS selectors)
                                                         ↓
                                              Rule Engine (14 operators)
                                                         ↓
                                              State Store (SQLite)
                                                         ↓
                                          Notification Dispatcher → Channels
```

Each tracker runs on its own schedule:

1. **Fetch** the page using HTTP or a headless browser
2. **Extract** values using CSS selectors with optional transforms
3. **Evaluate** rules against current and previous values
4. **Notify** through configured channels if conditions are met
5. **Store** values and notification history in SQLite

## Example: Track a Product Price

```yaml
trackers:
  amazon_widget:
    name: "Amazon - Widget Price"
    engine: http
    url: "https://www.amazon.com/dp/B0EXAMPLE"
    schedule:
      interval: 300          # every 5 minutes
      retry_count: 2         # retry twice on failure
      retry_delay: 10        # 10s, then 20s backoff

    extract:
      - name: price
        selector: "span.a-price .a-offscreen"
        attribute: text
        transform: [strip, "regex_extract('\\$([\\d.]+)')", to_number]
      - name: title
        selector: "#productTitle"
        attribute: text
        transform: [strip]

    rules:
      - condition:
          field: price
          operator: less_than
          value: 25
        message: "${title} is now $${price}!"
```

## Configuration

The entire system is driven by a single `config.yaml`. See [config.example.yaml](config.example.yaml) for a fully documented template covering all options.

### Engines

| Engine | Best For | Speed | JS Support |
|--------|----------|-------|------------|
| `http` | APIs, simple HTML, price pages | Fast (<500ms) | None |
| `browser` | JS-rendered pages, login-required sites | Slower (2-5s) | Full |

### Extraction

Extract values from pages using CSS selectors:

```yaml
extract:
  - name: price
    selector: ".price-tag span"
    attribute: text              # text, html, inner_html, or any HTML attribute
    transform: [strip, to_number]
```

**Available transforms:**

| Transform | Description |
|-----------|-------------|
| `strip` | Remove leading/trailing whitespace |
| `lowercase` | Convert to lowercase |
| `uppercase` | Convert to uppercase |
| `to_number` | Extract numeric value (removes `$`, `,`, etc.) |
| `hash_md5` | MD5 hash (useful for change detection) |
| `first_line` | First line only |
| `collapse_whitespace` | Collapse all whitespace to single spaces |
| `regex_extract('pattern')` | Extract first regex capture group |
| `truncate(N)` | Truncate to N characters |

### Rule Operators

| Operator | Description | Requires Value | Uses Previous |
|----------|-------------|:--------------:|:-------------:|
| `equals` | Exact string match | Yes | No |
| `not_equals` | Not equal | Yes | No |
| `contains` | Substring match | Yes | No |
| `not_contains` | Substring not present | Yes | No |
| `regex_match` | Regex pattern match | Yes | No |
| `less_than` | Numeric less than | Yes | No |
| `greater_than` | Numeric greater than | Yes | No |
| `changed` | Value differs from last check | No | Yes |
| `appeared` | Was null, now has value | No | Yes |
| `disappeared` | Had value, now null | No | Yes |
| `decreased_by_percent` | Dropped by N% or more | Yes | Yes |
| `increased_by_percent` | Rose by N% or more | Yes | Yes |
| `exists` | Value is not null | No | No |
| `not_exists` | Value is null | No | No |

Rules support **compound conditions** with `and`/`or`:

```yaml
rules:
  - condition:
      operator: and
      conditions:
        - field: price
          operator: less_than
          value: 300
        - field: stock
          operator: contains
          value: "In Stock"
    message: "Deal alert: ${price} and in stock!"
```

### Notification Channels

| Channel | Cost | Speed | Setup |
|---------|------|-------|-------|
| **Ntfy.sh** | Free | Instant | 1 min — no signup needed |
| **Pushover** | $5 once | Instant | 5 min |
| **Telegram** | Free | Instant | 10 min (create bot) |
| **Email** | Free | 1-30s | 5 min (SMTP config) |
| **Webhook** | Free | Instant | Varies (IFTTT, Slack, Discord) |

Configure channels once, then reference them by name in any tracker:

```yaml
notifications:
  channels:
    phone:
      type: ntfy
      topic: "my-web-alerts"
  defaults:
    channels: [phone]
    cooldown: 300              # don't re-notify within 5 minutes
```

### Anti-Detection

```yaml
trackers:
  my_tracker:
    proxy: "http://user:pass@proxy:8080"    # per-tracker proxy
    user_agents:                             # custom UA rotation
      - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
      - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
    schedule:
      interval: 60
      jitter: 10                # random ±10s delay
      active_hours: "07:00-21:00"
```

If no custom `user_agents` are specified, the system rotates through a built-in pool of 10 common browser user agents.

### Retry with Backoff

```yaml
schedule:
  retry_count: 3       # max retries on failure (default: 0)
  retry_delay: 5        # initial delay in seconds (doubles each retry: 5s, 10s, 20s)
```

## CLI Reference

```bash
# Core
webtracker run                       # Run all trackers continuously
webtracker test <tracker_id>         # Run one tracker once, show results
webtracker status                    # Show status of all trackers
webtracker history <tracker_id>      # View value history

# Config
webtracker config validate           # Validate config.yaml

# Notifications
webtracker notify test -ch <channel> # Send a test notification
webtracker notify history            # View notification log

# Auth (browser profiles)
webtracker auth setup <profile>      # Open browser for manual login
webtracker auth export-cookies <profile> -o cookies.json
webtracker auth list                 # List saved profiles

# Dashboard
webtracker dashboard                 # Start web UI on :8080
webtracker dashboard -p 3000         # Custom port
```

## Docker

```bash
# Run tracker + dashboard
docker compose up -d

# View logs
docker compose logs -f webtracker

# Set up browser profile interactively
docker compose run --rm webtracker auth setup my_profile --url https://example.com
```

The `docker-compose.yaml` includes two services:
- **webtracker** — runs all trackers continuously
- **dashboard** — web UI on port 8080, read-only access to the state database

## Project Structure

```
web-tracking/
├── config.yaml                  # your configuration
├── config.example.yaml          # documented template
├── docker-compose.yaml
├── Dockerfile
├── pyproject.toml
│
├── src/webtracker/
│   ├── cli.py                   # click CLI commands
│   ├── config.py                # YAML loader + Pydantic models
│   ├── scheduler.py             # async scheduler with retry
│   ├── dashboard.py             # FastAPI web dashboard
│   │
│   ├── engine/                  # page fetching
│   │   ├── base.py              # FetchResult dataclass
│   │   ├── http.py              # httpx engine (per-proxy client pooling)
│   │   ├── browser.py           # Playwright engine (cached contexts)
│   │   └── useragents.py        # UA rotation
│   │
│   ├── extract/                 # data extraction
│   │   ├── css.py               # CSS selector extraction
│   │   └── transforms.py        # strip, to_number, regex, hash, etc.
│   │
│   ├── rules/                   # condition evaluation
│   │   ├── engine.py            # rule evaluation + message formatting
│   │   └── operators.py         # 14 operators
│   │
│   ├── notify/                  # notification channels
│   │   ├── base.py              # abstract Notifier
│   │   ├── dispatcher.py        # routing, cooldown, concurrent sends
│   │   ├── ntfy.py
│   │   ├── pushover.py
│   │   ├── telegram.py
│   │   ├── email.py             # async SMTP via asyncio.to_thread
│   │   └── webhook.py
│   │
│   ├── state/
│   │   └── store.py             # SQLite with WAL mode
│   │
│   └── auth/
│       ├── cookies.py           # cookie load/save/convert
│       └── profiles.py          # browser profile management
│
├── tests/                       # 58 tests
│   ├── test_config.py
│   ├── test_extractors.py
│   ├── test_rules.py
│   ├── test_state.py
│   ├── test_retry.py
│   └── test_useragents.py
│
├── data/                        # SQLite database
├── browser_profiles/            # persistent browser sessions
└── cookies/                     # exported cookie files
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev,dashboard]"
playwright install chromium

# Run tests
python -m pytest tests/ -v

# Run tests with coverage
python -m pytest tests/ -v --tb=short
```

## License

MIT
