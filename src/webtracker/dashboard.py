"""Web dashboard for monitoring tracker status, values, and notifications."""

from __future__ import annotations

import time as _time
from datetime import datetime

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from webtracker.config import AppConfig
from webtracker.state.store import StateStore

_start_time = _time.time()


def create_app(config: AppConfig) -> FastAPI:
    """Create a FastAPI dashboard app bound to the given config."""
    store = StateStore(config.settings.state_db)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        store.close()

    app = FastAPI(title="WebTracker Dashboard", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _DASHBOARD_HTML

    @app.get("/api/health")
    async def health():
        uptime = _time.time() - _start_time
        return {
            "status": "ok",
            "uptime_seconds": round(uptime),
            "tracker_count": len(config.trackers),
        }

    @app.get("/api/trackers")
    async def trackers():
        result = []
        for tid, tracker in config.trackers.items():
            values = store.get_values(tid)
            errors = store.consecutive_error_count(tid)
            error_threshold = config.notifications.defaults.error_threshold

            if errors >= error_threshold:
                status = "error"
            elif values:
                status = "ok"
            else:
                status = "pending"

            result.append({
                "id": tid,
                "name": tracker.name,
                "engine": tracker.engine.value,
                "url": tracker.url,
                "interval": tracker.schedule.interval,
                "proxy": tracker.proxy,
                "status": status,
                "error_count": errors,
                "values": values,
            })
        return result

    @app.get("/api/trackers/{tracker_id}/history")
    async def tracker_history(
        tracker_id: str,
        field: str | None = Query(None),
        limit: int = Query(50, le=500),
    ):
        entries = store.get_history(tracker_id, field=field, limit=limit)
        return [
            {
                "field": e["field_name"],
                "value": e["value"],
                "time": datetime.fromtimestamp(e["recorded_at"]).isoformat(),
            }
            for e in entries
        ]

    @app.get("/api/notifications")
    async def notifications(
        tracker: str | None = Query(None),
        limit: int = Query(50, le=500),
    ):
        entries = store.get_notification_history(tracker_id=tracker, limit=limit)
        return [
            {
                "tracker_id": e["tracker_id"],
                "channel": e["channel"],
                "message": e["message"],
                "time": datetime.fromtimestamp(e["sent_at"]).isoformat(),
            }
            for e in entries
        ]

    return app


# ── Inline Dashboard HTML ────────────────────────────────
# Single-page app with vanilla JS. No build step needed.

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WebTracker Dashboard</title>
<style>
  :root { --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a; --text: #e1e4ed; --dim: #6b7280; --green: #22c55e; --yellow: #eab308; --red: #ef4444; --blue: #3b82f6; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 24px; margin-bottom: 8px; }
  .subtitle { color: var(--dim); margin-bottom: 24px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .card-title { font-size: 16px; font-weight: 600; }
  .badge { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .badge-ok { background: #16291a; color: var(--green); }
  .badge-pending { background: #291f0a; color: var(--yellow); }
  .badge-error { background: #2d1215; color: var(--red); }
  .card-meta { color: var(--dim); font-size: 13px; margin-bottom: 12px; }
  .values-table { width: 100%; font-size: 13px; }
  .values-table td { padding: 4px 0; }
  .values-table td:first-child { color: var(--dim); width: 40%; }
  .values-table td:last-child { font-family: 'SF Mono', 'Fira Code', monospace; text-align: right; }
  .section-title { font-size: 18px; margin-bottom: 16px; }
  table.log { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.log th { text-align: left; color: var(--dim); font-weight: 500; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  table.log td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  table.log tr:last-child td { border: none; }
  .msg-cell { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .health { display: flex; gap: 24px; margin-bottom: 24px; font-size: 14px; }
  .health-item { color: var(--dim); }
  .health-item span { color: var(--text); font-weight: 500; }
  .refresh-note { color: var(--dim); font-size: 12px; }
  a { color: var(--blue); text-decoration: none; }
  .empty { color: var(--dim); font-style: italic; padding: 16px 0; }
</style>
</head>
<body>
  <h1>WebTracker Dashboard</h1>
  <div class="health" id="health"></div>

  <h2 class="section-title">Trackers</h2>
  <div class="grid" id="trackers"></div>

  <h2 class="section-title">Recent Notifications</h2>
  <div class="card">
    <table class="log" id="notifications">
      <thead><tr><th>Time</th><th>Tracker</th><th>Channel</th><th>Message</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <br><div class="refresh-note">Auto-refreshes every 30 seconds</div>

<script>
const API = '';

function badge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

function relTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString();
}

async function loadHealth() {
  const r = await fetch(API + '/api/health');
  const h = await r.json();
  const mins = Math.floor(h.uptime_seconds / 60);
  document.getElementById('health').innerHTML = `
    <div class="health-item">Status: <span style="color:var(--green)">Running</span></div>
    <div class="health-item">Trackers: <span>${h.tracker_count}</span></div>
    <div class="health-item">Uptime: <span>${mins}m</span></div>
  `;
}

async function loadTrackers() {
  const r = await fetch(API + '/api/trackers');
  const trackers = await r.json();
  const el = document.getElementById('trackers');
  if (!trackers.length) { el.innerHTML = '<div class="empty">No trackers configured</div>'; return; }
  el.innerHTML = trackers.map(t => {
    const vals = Object.entries(t.values || {});
    const valRows = vals.length
      ? vals.map(([k,v]) => `<tr><td>${k}</td><td>${v ?? '<em>null</em>'}</td></tr>`).join('')
      : '<tr><td colspan="2" class="empty">No data yet</td></tr>';
    const proxy = t.proxy ? `<br>Proxy: ${t.proxy}` : '';
    return `<div class="card">
      <div class="card-header">
        <span class="card-title">${t.name}</span>
        ${badge(t.status)}
      </div>
      <div class="card-meta">${t.engine.toUpperCase()} &middot; every ${t.interval}s${t.error_count ? ` &middot; <span style="color:var(--red)">${t.error_count} errors</span>` : ''}${proxy}</div>
      <table class="values-table">${valRows}</table>
    </div>`;
  }).join('');
}

async function loadNotifications() {
  const r = await fetch(API + '/api/notifications?limit=20');
  const notifs = await r.json();
  const tbody = document.querySelector('#notifications tbody');
  if (!notifs.length) { tbody.innerHTML = '<tr><td colspan="4" class="empty">No notifications yet</td></tr>'; return; }
  tbody.innerHTML = notifs.map(n => `<tr>
    <td>${relTime(n.time)}</td>
    <td>${n.tracker_id}</td>
    <td>${n.channel}</td>
    <td class="msg-cell">${n.message}</td>
  </tr>`).join('');
}

async function refresh() {
  try { await Promise.all([loadHealth(), loadTrackers(), loadNotifications()]); }
  catch(e) { console.error('Refresh failed:', e); }
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""
