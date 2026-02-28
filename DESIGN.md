# Web Tracking Notification System — Architecture Design

## Overview

A flexible, plugin-based system that monitors web pages for specific conditions and sends instant notifications through multiple channels. Designed to be generic enough to track anything — stock availability, price drops, new posts, content changes — while being simple to configure.

## Use Cases

| # | Use Case | What to Track | Condition |
|---|----------|---------------|-----------|
| 1 | Best Buy in-stock | Product page availability | Button changes from "Sold Out" → "Add to Cart" |
| 2 | Amazon price drop | Product price element | Price < threshold OR price dropped > X% |
| 3 | Facebook new post | User's profile/page feed | New post appears (newer than last seen) |
| 4 | Too Good To Go | Available bags count | Stock count > 0 or changes from unavailable → available |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    YAML Configuration                    │
│  (trackers, rules, notifications, schedules)            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                     Scheduler                            │
│              (APScheduler / cron-like)                   │
│  Per-tracker intervals, jitter, backoff on failure       │
└──────────┬───────────────────────────────┬──────────────┘
           │                               │
┌──────────▼──────────┐     ┌──────────────▼──────────────┐
│   Browser Engine     │     │      HTTP Engine            │
│   (Playwright)       │     │      (httpx/requests)       │
│                      │     │                             │
│ - JS-heavy pages     │     │ - API endpoints             │
│ - Login-required     │     │ - Simple HTML pages         │
│ - Cookie/profile     │     │ - JSON responses            │
│   auth support       │     │ - Faster, lighter           │
└──────────┬──────────┘     └──────────────┬──────────────┘
           │                               │
           └───────────┬───────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Extractor Layer                        │
│                                                         │
│  CSS Selector  │  XPath  │  JSONPath  │  Regex          │
│  Text content  │  Attribute value  │  Element existence  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    Rule Engine                           │
│                                                         │
│  Conditions:                                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │ equals, contains, regex_match, exists            │    │
│  │ less_than, greater_than, changed, not_equals     │    │
│  │ appeared, disappeared                            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Combinators:  and / or / not                           │
│  Transforms:   to_number, strip, lowercase, first_match │
└──────────────────────┬──────────────────────────────────┘
                       │ (condition met?)
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  State Manager                          │
│                  (SQLite)                                │
│                                                         │
│  - Last extracted value per tracker                     │
│  - Last notification time (cooldown enforcement)        │
│  - History of changes (for trend analysis)              │
│  - Error/retry counts                                   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│               Notification Dispatcher                    │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────────┐  │
│  │ Ntfy.sh  │ │ Pushover │ │Telegram│ │ Email(SMTP) │  │
│  └──────────┘ └──────────┘ └────────┘ └─────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────────┐  │
│  │  IFTTT   │ │ SMS/Twilio│ │ Webhook (generic)     │  │
│  └──────────┘ └──────────┘ └────────────────────────┘  │
│                                                         │
│  Features: priority levels, cooldown, dedup, templates  │
└─────────────────────────────────────────────────────────┘
```

---

## Configuration Design (YAML)

The entire system is driven by a single `config.yaml` file. This is the core
of the flexibility — you never write code to add a new tracker.

```yaml
# ─── Global Settings ─────────────────────────────────────
settings:
  browser:
    headless: true
    user_data_dir: "./browser_profiles/default"  # persistent login sessions
    default_timeout: 30000  # ms
  state_db: "./data/state.db"
  log_level: info

# ─── Notification Channels ───────────────────────────────
notifications:
  channels:
    ntfy_phone:
      type: ntfy
      server: "https://ntfy.sh"     # or self-hosted
      topic: "my-web-alerts"
      priority: high                  # default priority

    pushover_urgent:
      type: pushover
      user_key: "${PUSHOVER_USER}"    # env var reference
      api_token: "${PUSHOVER_TOKEN}"
      priority: emergency             # will repeat until acknowledged
      sound: "siren"

    telegram:
      type: telegram
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"

    email_backup:
      type: email
      smtp_host: "smtp.gmail.com"
      smtp_port: 587
      username: "${EMAIL_USER}"
      password: "${EMAIL_PASS}"
      from: "alerts@example.com"
      to: "me@example.com"

    ifttt:
      type: webhook
      url: "https://maker.ifttt.com/trigger/{event}/with/key/${IFTTT_KEY}"
      method: POST

  # Default channels for all trackers (can be overridden per tracker)
  defaults:
    channels: [ntfy_phone]
    cooldown: 300          # don't re-notify for same condition within 5 min
    on_error_notify: true  # notify if tracker fails N times in a row
    error_threshold: 3

# ─── Trackers ────────────────────────────────────────────
trackers:
  # ── Use Case 1: Best Buy In-Stock ───────────────────
  bestbuy_ps5:
    name: "Best Buy PS5 Stock"
    engine: browser                    # needs JS rendering
    url: "https://www.bestbuy.com/site/product/6523167.p"
    schedule:
      interval: 60                     # check every 60 seconds
      jitter: 10                       # random ±10s to avoid detection
    auth: null                         # no login needed

    extract:
      - name: button_text
        selector: "button.add-to-cart-button"
        attribute: text
      - name: price
        selector: ".priceView-customer-price span"
        attribute: text
        transform: [strip, to_number]

    rules:
      - condition:
          field: button_text
          operator: contains
          value: "Add to Cart"
        message: "PS5 IN STOCK at Best Buy! Price: ${price}"
        channels: [ntfy_phone, pushover_urgent, telegram]
        priority: emergency

  # ── Use Case 2: Amazon Price Drop ───────────────────
  amazon_headphones:
    name: "Sony WH-1000XM5 Price"
    engine: http                       # Amazon works without JS for price
    url: "https://www.amazon.com/dp/B0BX2L8PBT"
    headers:
      User-Agent: "Mozilla/5.0 ..."   # custom headers
    schedule:
      interval: 300                    # every 5 min
    auth:
      type: cookies
      file: "./cookies/amazon.json"

    extract:
      - name: price
        selector: "span.a-price .a-offscreen"
        attribute: text
        transform: [strip, regex_extract("\\$([\\d.]+)"), to_number]
      - name: title
        selector: "#productTitle"
        attribute: text
        transform: [strip]

    rules:
      - condition:
          field: price
          operator: less_than
          value: 280
        message: "${title} dropped to $${price}!"
        channels: [ntfy_phone, telegram]
      - condition:
          field: price
          operator: decreased_by_percent
          value: 10     # 10% drop from last seen price
        message: "${title} price dropped ${change_percent}%! Now $${price}"
        channels: [ntfy_phone]

  # ── Use Case 3: Facebook Post Monitor ───────────────
  facebook_friend:
    name: "Facebook - John's Posts"
    engine: browser
    url: "https://www.facebook.com/johndoe"
    schedule:
      interval: 30                     # every 30 seconds for near-instant
    auth:
      type: browser_profile
      profile: "facebook_logged_in"    # named profile directory

    # Wait for dynamic content to load
    wait_for:
      selector: "[data-pagelet='ProfileTimeline']"
      timeout: 10000

    # Optional: perform actions before extracting
    actions:
      - type: scroll
        amount: 500                    # scroll down to load posts

    extract:
      - name: latest_post_id
        selector: "[role='article']:first-of-type"
        attribute: "data-post-id"      # or aria-label, depends on FB's DOM
      - name: latest_post_text
        selector: "[role='article']:first-of-type [data-ad-preview='message']"
        attribute: text
      - name: latest_post_time
        selector: "[role='article']:first-of-type abbr"
        attribute: "data-utime"

    rules:
      - condition:
          field: latest_post_id
          operator: changed
        message: "New post from John: ${latest_post_text}"
        channels: [ntfy_phone, pushover_urgent]
        priority: high

  # ── Use Case 4: Too Good To Go ──────────────────────
  tgtg_bakery:
    name: "TGTG - Local Bakery"
    engine: browser
    url: "https://share.toogoodtogo.com/item/123456"
    schedule:
      interval: 45
      active_hours: "07:00-21:00"      # only check during business hours
    auth:
      type: browser_profile
      profile: "tgtg_logged_in"

    extract:
      - name: stock_text
        selector: ".item-availability"
        attribute: text
      - name: quantity
        selector: ".item-quantity"
        attribute: text
        transform: [strip, to_number]

    rules:
      - condition:
          field: stock_text
          operator: not_contains
          value: "Sold out"
        message: "TGTG bags available at Local Bakery! Qty: ${quantity}"
        channels: [ntfy_phone, pushover_urgent]
        priority: emergency

  # ── Generic Example: Any page change ────────────────
  custom_page_watch:
    name: "Watch for page changes"
    engine: http
    url: "https://example.com/some-page"
    schedule:
      interval: 600
    extract:
      - name: content_hash
        selector: "#main-content"
        attribute: text
        transform: [strip, hash_md5]   # hash the content for change detection
    rules:
      - condition:
          field: content_hash
          operator: changed
        message: "Page content changed on example.com!"
        channels: [ntfy_phone]
```

---

## Key Design Decisions

### 1. Dual Engine (Browser + HTTP)

Not every page needs a full browser. The system supports two engines:

| | Browser (Playwright) | HTTP (httpx) |
|---|---|---|
| **Speed** | Slow (2-5s per check) | Fast (<500ms) |
| **Resource** | High (headless Chrome) | Minimal |
| **JS Support** | Full | None |
| **Login** | Easy (real browser) | Cookie-based only |
| **Best for** | Facebook, TGTG, JS-heavy | Amazon, APIs, simple HTML |

The engine is chosen per-tracker, so you use the lightest option that works.

### 2. Persistent Browser Profiles

For sites like Facebook and TGTG where login is required:

1. **First-time setup**: Run `python -m webtracker auth setup facebook_logged_in`
   - Opens a visible browser window
   - You log in manually, complete 2FA, etc.
   - Browser profile is saved to `./browser_profiles/facebook_logged_in/`
2. **Subsequent runs**: Tracker uses this profile automatically — cookies, localStorage, everything persists.
3. **Cookie export**: For simpler cases, export cookies as JSON and reference the file.

### 3. Rule Engine — Why Declarative?

Instead of writing Python for each tracker:
- **Non-programmers** can add trackers by editing YAML
- **No code changes** needed for new trackers
- Rules are **composable**: combine conditions with and/or/not
- Rules are **auditable**: easy to see what you're tracking

Advanced rules support:
```yaml
rules:
  - condition:
      operator: and
      conditions:
        - field: price
          operator: less_than
          value: 300
        - field: rating
          operator: greater_than
          value: 4.0
    message: "Good deal: ${title} at $${price} with ${rating}★"
```

### 4. State Management (SQLite)

SQLite stores:
- **Last seen values** — for `changed`, `decreased_by_percent` operators
- **Notification history** — cooldown enforcement, dedup
- **Error tracking** — retry counts, last error message
- **Value history** — optional, for trend analysis (e.g., price over time)

Why SQLite: zero setup, file-based (easy backup), survives restarts, fast for this scale.

### 5. Anti-Detection / Resilience

- **Request jitter**: Random delay ±N seconds to avoid fixed-interval detection
- **User-Agent rotation**: Configurable per tracker
- **Active hours**: Only check during specified time windows
- **Backoff on error**: Exponential backoff if a tracker fails repeatedly
- **Proxy support**: Optional per-tracker proxy configuration

---

## Project Structure

```
web-tracking/
├── config.yaml                  # main configuration
├── config.example.yaml          # template with all options documented
├── docker-compose.yaml          # one-command deployment
├── Dockerfile
├── pyproject.toml               # Python project config (dependencies)
│
├── src/
│   └── webtracker/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point
│       ├── cli.py               # click-based CLI commands
│       ├── config.py            # YAML config loader & validation
│       ├── scheduler.py         # APScheduler orchestration
│       │
│       ├── engine/              # page fetching
│       │   ├── __init__.py
│       │   ├── base.py          # abstract Engine interface
│       │   ├── browser.py       # Playwright browser engine
│       │   └── http.py          # httpx HTTP engine
│       │
│       ├── extract/             # data extraction from pages
│       │   ├── __init__.py
│       │   ├── base.py          # abstract Extractor
│       │   ├── css.py           # CSS selector extraction
│       │   ├── xpath.py         # XPath extraction
│       │   ├── jsonpath.py      # JSON path extraction (for APIs)
│       │   └── transforms.py    # strip, to_number, regex, hash, etc.
│       │
│       ├── rules/               # condition evaluation
│       │   ├── __init__.py
│       │   ├── engine.py        # rule evaluation logic
│       │   └── operators.py     # equals, less_than, changed, etc.
│       │
│       ├── notify/              # notification channels
│       │   ├── __init__.py
│       │   ├── base.py          # abstract Notifier
│       │   ├── ntfy.py
│       │   ├── pushover.py
│       │   ├── telegram.py
│       │   ├── email.py
│       │   ├── webhook.py       # generic webhook (covers IFTTT, etc.)
│       │   └── dispatcher.py    # routes to channels, handles cooldown
│       │
│       ├── state/               # persistence
│       │   ├── __init__.py
│       │   └── store.py         # SQLite state management
│       │
│       └── auth/                # authentication helpers
│           ├── __init__.py
│           ├── cookies.py       # cookie import/export
│           └── profiles.py      # browser profile management
│
├── browser_profiles/            # persistent browser sessions
├── cookies/                     # exported cookie files
├── data/                        # SQLite DB, logs
│
└── tests/
    ├── test_config.py
    ├── test_rules.py
    ├── test_extractors.py
    └── test_notifications.py
```

---

## CLI Commands

```bash
# Run the tracker daemon
webtracker run

# Run a single tracker once (for testing)
webtracker test bestbuy_ps5

# Setup browser profile (opens visible browser for manual login)
webtracker auth setup <profile_name> [--url <start_url>]

# Export cookies from a browser profile
webtracker auth export-cookies <profile_name> --output cookies/site.json

# List all configured trackers and their status
webtracker status

# View history for a tracker
webtracker history amazon_headphones --last 50

# Send a test notification
webtracker notify test --channel ntfy_phone --message "Test alert!"

# Validate configuration
webtracker config validate
```

---

## Notification Channel Comparison

| Channel | Cost | Speed | Setup Effort | Rich Content | Priority Levels |
|---------|------|-------|-------------|-------------|-----------------|
| **Ntfy.sh** | Free | Instant | 1 min | Links, emoji | Yes (1-5) |
| **Pushover** | $5 once | Instant | 5 min | Images, links, sounds | Yes + emergency repeat |
| **Telegram** | Free | Instant | 10 min | Full markdown, images | No (manual) |
| **Email** | Free | 1-30s | 5 min | Full HTML | No |
| **IFTTT** | Free (limited) | 1-15 min | 5 min | Limited | No |
| **SMS (Twilio)** | ~$0.01/msg | Instant | 15 min | Text only | No |
| **Webhook** | Free | Instant | Varies | JSON payload | Custom |

**My recommendation**: Start with **Ntfy.sh** (zero friction) + **Pushover** (for critical alerts that repeat until acknowledged). Add others later as needed.

---

## Docker Deployment

```yaml
# docker-compose.yaml
services:
  webtracker:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data                 # SQLite persistence
      - ./browser_profiles:/app/browser_profiles
      - ./cookies:/app/cookies:ro
    environment:
      - PUSHOVER_USER=${PUSHOVER_USER}
      - PUSHOVER_TOKEN=${PUSHOVER_TOKEN}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
    # For browser profile setup (run once, interactively):
    # docker compose run --rm -e DISPLAY=$DISPLAY webtracker auth setup facebook
```

---

## Implementation Phases

### Phase 1 — Core (MVP)
- Config loader with validation (Pydantic)
- HTTP engine (httpx) + CSS selector extraction
- Rule engine with basic operators (equals, contains, less_than, changed)
- SQLite state store
- Ntfy.sh notification channel
- CLI: `run`, `test`, `notify test`
- **Deliverable**: Can track Amazon price, Best Buy stock (simple pages)

### Phase 2 — Browser Engine
- Playwright browser engine
- Browser profile management (auth setup/teardown)
- Cookie import/export
- Wait-for and scroll actions
- **Deliverable**: Can track Facebook posts, TGTG, any JS-heavy page

### Phase 3 — Full Notifications
- Pushover, Telegram, Email, Webhook channels
- Notification templates with variable substitution
- Cooldown and deduplication
- Priority escalation (e.g., notify email after 3 failed pushes)

### Phase 4 — Polish
- Docker packaging
- Active hours / schedule windows
- Error notification (alert if tracker broken for N checks)
- Value history + trends
- Anti-detection features (jitter, user-agent rotation, proxy)
- Optional web dashboard for status monitoring

---

## Key Dependencies

```
playwright          # browser automation
httpx               # async HTTP client
beautifulsoup4      # HTML parsing
lxml                # XPath support
pyyaml              # config parsing
pydantic            # config validation
apscheduler         # job scheduling
click               # CLI framework
rich                # pretty terminal output
```

---

## Extensibility Points

The architecture is designed so you can extend it without modifying core code:

1. **New notification channel** — Add a file in `notify/`, implement `Notifier` base class
2. **New extraction method** — Add to `extract/`, register in config schema
3. **New transform function** — Add to `transforms.py`, reference in YAML
4. **New rule operator** — Add to `operators.py`, reference in YAML
5. **New engine** — Add to `engine/` (e.g., a gRPC or WebSocket engine)
6. **Tracker presets** — Share YAML snippets for common sites (community templates)
