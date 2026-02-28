# Setup Guide

This guide walks you through installing, configuring, and running WebTracker from scratch.

## Prerequisites

- Python 3.11 or later
- pip (Python package manager)
- Docker and Docker Compose (optional, for containerized deployment)

## Installation

### Option A: Local Install

```bash
# Clone the repo
git clone <repo-url> web-tracking
cd web-tracking

# Install the package with all optional dependencies
pip install -e ".[dev,dashboard]"

# Install the Playwright browser (needed for browser engine)
playwright install chromium
playwright install-deps chromium    # installs system-level dependencies
```

### Option B: Docker

```bash
git clone <repo-url> web-tracking
cd web-tracking

# Build and run (handles all dependencies automatically)
docker compose up -d
```

The Docker image installs Chromium and all Python dependencies during build.

## Configuration

### 1. Create Your Config File

```bash
cp config.example.yaml config.yaml
```

### 2. Set Up a Notification Channel

Start with **Ntfy.sh** — it requires zero signup. Just pick a unique topic name and install the [ntfy app](https://ntfy.sh) on your phone.

Open `config.yaml` and configure the notifications section:

```yaml
notifications:
  channels:
    phone:
      type: ntfy
      server: "https://ntfy.sh"
      topic: "my-secret-alerts-topic"    # pick something unique and hard to guess
      priority: high

  defaults:
    channels: [phone]
    cooldown: 300              # 5 minute cooldown between re-notifications
    on_error_notify: true      # get notified if a tracker fails repeatedly
    error_threshold: 3         # after 3 consecutive failures
```

To test that notifications work:

```bash
webtracker notify test -ch phone -m "Hello from WebTracker!"
```

You should receive a push notification on your phone.

#### Other Channels

**Pushover** (one-time $5 purchase, reliable with priority levels):

```yaml
pushover_alerts:
  type: pushover
  user_key: "${PUSHOVER_USER}"        # set via environment variable
  api_token: "${PUSHOVER_TOKEN}"
  priority: 0                         # -1=low, 0=normal, 1=high, 2=emergency
```

**Telegram** (free, rich formatting):

```yaml
telegram:
  type: telegram
  bot_token: "${TELEGRAM_BOT_TOKEN}"  # create via @BotFather
  chat_id: "${TELEGRAM_CHAT_ID}"      # get via @userinfobot
```

**Email** (SMTP):

```yaml
email:
  type: email
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  username: "${EMAIL_USER}"
  password: "${EMAIL_PASS}"           # use app-specific password for Gmail
  from: "alerts@example.com"
  to: "me@example.com"
```

**Webhook** (IFTTT, Slack, Discord, etc.):

```yaml
slack_webhook:
  type: webhook
  url: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
  method: POST
```

### 3. Environment Variables

Sensitive values like API keys and passwords should be set as environment variables. WebTracker resolves `${VAR_NAME}` references in config values at load time.

```bash
# Set in your shell or .env file
export PUSHOVER_USER="your-user-key"
export PUSHOVER_TOKEN="your-api-token"
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_CHAT_ID="987654321"
```

For Docker, add them to a `.env` file in the project root:

```
PUSHOVER_USER=your-user-key
PUSHOVER_TOKEN=your-api-token
```

### 4. Add Your First Tracker

Add a tracker to the `trackers` section of `config.yaml`. Here's a simple example that watches a page for changes:

```yaml
trackers:
  my_page:
    name: "Watch Example Page"
    engine: http
    url: "https://example.com"
    schedule:
      interval: 600            # check every 10 minutes

    extract:
      - name: heading
        selector: "h1"
        attribute: text
        transform: [strip]

    rules:
      - condition:
          field: heading
          operator: changed
        message: "Page heading changed to: ${heading}"
```

### 5. Validate Your Config

```bash
webtracker config validate
```

This checks that all YAML is valid, all required fields are present, and all referenced channels exist.

### 6. Test Your Tracker

Run a single tracker once to see what it extracts:

```bash
webtracker test my_page
```

This will fetch the page, extract values, evaluate rules, and display the results in a table — without sending any notifications for the first run (since there's no previous value to compare against).

## Choosing an Engine

### HTTP Engine (`engine: http`)

Use for pages that render their content server-side:

- Product pages on most e-commerce sites
- API endpoints returning JSON or HTML
- Static pages, blogs, news sites
- Anything where the data is in the initial HTML response

### Browser Engine (`engine: browser`)

Use for pages that require JavaScript to render:

- Single-page applications (React, Vue, Angular)
- Sites that load content dynamically
- Pages behind login walls that need browser cookies/sessions
- Sites with anti-bot protections that check for browser fingerprints

The browser engine is slower and uses more resources. Always try HTTP first.

## Authentication

### Cookie-Based Auth (HTTP Engine)

For sites where you can export cookies:

1. Log in to the site in your browser
2. Export cookies using a browser extension (e.g., "Cookie Editor")
3. Save as JSON to `cookies/site.json`
4. Reference in your tracker:

```yaml
my_tracker:
  engine: http
  auth:
    type: cookies
    file: "./cookies/site.json"
```

The cookie file should be a JSON array of cookie objects or a simple `{"name": "value"}` dict.

### Browser Profile Auth (Browser Engine)

For sites that need a full browser session:

1. Run the auth setup command:

```bash
webtracker auth setup my_profile --url https://facebook.com
```

2. A browser window opens — log in manually, complete 2FA, accept prompts
3. Close the browser window when done
4. Reference the profile in your tracker:

```yaml
my_tracker:
  engine: browser
  auth:
    type: browser_profile
    profile: "my_profile"
```

The browser profile persists cookies, localStorage, and all session data. You only need to set it up once.

To list saved profiles:

```bash
webtracker auth list
```

To export cookies from a profile:

```bash
webtracker auth export-cookies my_profile -o cookies/export.json
```

## Anti-Detection Settings

Websites may block or throttle automated requests. Use these settings to reduce detection:

### Jitter

Adds random variation to check intervals so requests don't arrive at exact fixed intervals:

```yaml
schedule:
  interval: 60
  jitter: 10       # actual interval will be 50-70 seconds
```

### Active Hours

Only run checks during certain hours (saves resources and reduces detection):

```yaml
schedule:
  active_hours: "07:00-21:00"
```

### User-Agent Rotation

By default, WebTracker rotates through a pool of 10 common browser user agents. You can specify custom ones per tracker:

```yaml
user_agents:
  - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
```

### Proxy

Route requests through a proxy on a per-tracker basis:

```yaml
proxy: "http://user:pass@proxy-server:8080"
```

## Retry and Error Handling

### Automatic Retries

Configure retries for transient failures (network errors, timeouts):

```yaml
schedule:
  retry_count: 3      # try up to 3 additional times
  retry_delay: 5       # first retry after 5s, then 10s, then 20s (exponential backoff)
```

### Error Notifications

When a tracker fails repeatedly, you can be notified:

```yaml
notifications:
  defaults:
    on_error_notify: true
    error_threshold: 3     # notify after 3 consecutive failures
```

## Running in Production

### Using Docker Compose (Recommended)

```bash
# Start both tracker and dashboard
docker compose up -d

# View tracker logs
docker compose logs -f webtracker

# View dashboard at http://localhost:8080
```

The `docker-compose.yaml` defines two services:

- **webtracker** — runs all trackers on their configured schedules
- **dashboard** — web UI on port 8080 showing tracker status, extracted values, and notification history

Both services share the `data/` volume so the dashboard can read the SQLite database.

### Using systemd (Without Docker)

Create `/etc/systemd/system/webtracker.service`:

```ini
[Unit]
Description=WebTracker
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/webtracker
ExecStart=/opt/webtracker/.venv/bin/webtracker run
Restart=always
RestartSec=10
Environment=PUSHOVER_USER=your-key
Environment=PUSHOVER_TOKEN=your-token

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now webtracker
```

### Web Dashboard

Start the dashboard to monitor your trackers in a browser:

```bash
# Local
webtracker dashboard

# Custom host/port
webtracker dashboard --host 0.0.0.0 -p 3000
```

The dashboard shows:
- Tracker status (green/yellow/red) with last extracted values
- Error counts and consecutive failure tracking
- Notification history with timestamps and messages
- Auto-refreshes every 30 seconds

The dashboard is read-only and requires the `dashboard` optional dependency:

```bash
pip install -e ".[dashboard]"
```

## Writing Effective Trackers

### Tips

1. **Start with HTTP** — it's faster and uses fewer resources. Only switch to browser if HTTP doesn't return the data you need.

2. **Use transforms wisely** — chain transforms to clean extracted values:
   ```yaml
   transform: [strip, lowercase]                          # clean text
   transform: [strip, "regex_extract('\\$(\\d+\\.\\d+)')", to_number]  # extract price
   transform: [strip, collapse_whitespace, hash_md5]      # detect any change
   ```

3. **Test selectors in your browser** — open DevTools, use `document.querySelector("your-selector")` to verify your CSS selector returns the right element.

4. **Use `changed` with `hash_md5`** for generic page change detection:
   ```yaml
   extract:
     - name: content_hash
       selector: "#main-content"
       attribute: text
       transform: [strip, collapse_whitespace, hash_md5]
   rules:
     - condition:
         field: content_hash
         operator: changed
       message: "Page content changed!"
   ```

5. **Set appropriate intervals** — don't poll more frequently than needed. Most use cases work fine at 60-300 second intervals.

6. **Use `wait_for`** with the browser engine to ensure dynamic content has loaded:
   ```yaml
   wait_for:
     selector: "[role='article']"
     timeout: 10000
   ```

### Message Templates

Rule messages support variable substitution:

| Variable | Description |
|----------|-------------|
| `${field_name}` | Current value of any extracted field |
| `${prev_field_name}` | Previous value of any extracted field |
| `${change_percent}` | Percentage change (for numeric fields) |

```yaml
message: "${title} dropped from $${prev_price} to $${price} (${change_percent}% off)!"
```

## Troubleshooting

### Config validation fails

```bash
webtracker config validate
```

Check for YAML syntax errors, missing required fields, or invalid operator names.

### Tracker extracts null values

1. Run with debug logging: `webtracker -c config.yaml test my_tracker`
2. Check if the CSS selector matches anything on the page
3. Try the `browser` engine if the page requires JavaScript
4. Verify the `attribute` is correct (`text`, `html`, or an HTML attribute name)

### Notifications not sending

1. Test the channel directly: `webtracker notify test -ch my_channel`
2. Check cooldown settings — you won't be re-notified within the cooldown window
3. Check environment variables are set for channels using `${VAR}` references

### Browser engine crashes

1. Make sure Playwright and Chromium are installed: `playwright install chromium`
2. In Docker, system dependencies are handled automatically
3. Check memory — each browser context uses ~100-200MB

### Dashboard won't start

```bash
pip install -e ".[dashboard]"    # install FastAPI + Uvicorn
webtracker dashboard
```
