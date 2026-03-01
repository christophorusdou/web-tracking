"""CLI commands for the web tracking notification system."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from webtracker.config import load_config

console = Console()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


@click.group()
@click.option("--config", "-c", default="config.yaml", help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """Web Tracking Notification System."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Run all trackers continuously."""
    from webtracker.scheduler import TrackerRunner

    config = load_config(ctx.obj["config_path"])
    _setup_logging(config.settings.log_level)

    runner = TrackerRunner(config)

    def handle_signal(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        runner.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    console.print(f"[green]Starting {len(config.trackers)} tracker(s)...[/green]")
    for name, tracker in config.trackers.items():
        console.print(f"  [cyan]{name}[/cyan] — {tracker.name} (every {tracker.schedule.interval}s)")

    asyncio.run(runner.run_all())


@cli.command()
@click.argument("tracker_id")
@click.pass_context
def test(ctx: click.Context, tracker_id: str) -> None:
    """Run a single tracker once and show results."""
    from webtracker.scheduler import TrackerRunner

    config = load_config(ctx.obj["config_path"])
    _setup_logging("debug")

    if tracker_id not in config.trackers:
        console.print(f"[red]Tracker '{tracker_id}' not found in config[/red]")
        console.print(f"Available: {', '.join(config.trackers.keys())}")
        sys.exit(1)

    runner = TrackerRunner(config)

    async def _run():
        try:
            values = await runner.run_once(tracker_id)
            console.print("\n[green]Extracted values:[/green]")
            table = Table()
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")
            for k, v in values.items():
                table.add_row(k, str(v) if v is not None else "[dim]None[/dim]")
            console.print(table)
        finally:
            await runner.close()

    asyncio.run(_run())


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show status of all configured trackers."""
    config = load_config(ctx.obj["config_path"])
    from webtracker.state.store import StateStore

    with StateStore(config.settings.state_db) as store:
        table = Table(title="Tracker Status")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Engine", style="yellow")
        table.add_column("Interval", style="green")
        table.add_column("Last Values", style="white")
        table.add_column("Errors", style="red")

        for tid, tracker in config.trackers.items():
            values = store.get_values(tid)
            errors = store.consecutive_error_count(tid)
            values_str = ", ".join(f"{k}={v}" for k, v in values.items()) if values else "[dim]no data yet[/dim]"

            table.add_row(
                tid,
                tracker.name,
                tracker.engine.value,
                f"{tracker.schedule.interval}s",
                values_str,
                str(errors) if errors > 0 else "[green]0[/green]",
            )

        console.print(table)


@cli.command()
@click.argument("tracker_id")
@click.option("--field", "-f", default=None, help="Filter by field name")
@click.option("--last", "-n", default=50, help="Number of entries to show")
@click.pass_context
def history(ctx: click.Context, tracker_id: str, field: str | None, last: int) -> None:
    """View value history for a tracker."""
    config = load_config(ctx.obj["config_path"])

    if tracker_id not in config.trackers:
        console.print(f"[red]Tracker '{tracker_id}' not found in config[/red]")
        console.print(f"Available: {', '.join(config.trackers.keys())}")
        sys.exit(1)

    from datetime import datetime

    from webtracker.state.store import StateStore

    with StateStore(config.settings.state_db) as store:
        entries = store.get_history(tracker_id, field=field, limit=last)

        if not entries:
            console.print(f"[yellow]No history for tracker '{tracker_id}'[/yellow]")
            return

        table = Table(title=f"History: {tracker_id}")
        table.add_column("Time", style="dim")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        for entry in entries:
            ts = datetime.fromtimestamp(entry["recorded_at"]).strftime("%Y-%m-%d %H:%M:%S")
            table.add_row(ts, entry["field_name"], str(entry["value"]) if entry["value"] else "[dim]None[/dim]")

        console.print(table)


@cli.command("config")
@click.argument("action", type=click.Choice(["validate"]))
@click.pass_context
def config_cmd(ctx: click.Context, action: str) -> None:
    """Validate configuration file."""
    try:
        config = load_config(ctx.obj["config_path"])
        console.print(f"[green]Config is valid![/green]")
        console.print(f"  Trackers: {len(config.trackers)}")
        console.print(f"  Channels: {len(config.notifications.channels)}")
        for name, tracker in config.trackers.items():
            console.print(f"  [cyan]{name}[/cyan]: {len(tracker.rules)} rule(s), engine={tracker.engine.value}")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Config validation failed:[/red] {e}")
        sys.exit(1)


# ── Notification Commands ────────────────────────────────


@cli.group("notify")
def notify_group() -> None:
    """Notification management commands."""


@notify_group.command("test")
@click.option("--channel", "-ch", required=True, help="Channel name to test")
@click.option("--message", "-m", default="Test notification from WebTracker!", help="Test message")
@click.pass_context
def notify_test(ctx: click.Context, channel: str, message: str) -> None:
    """Send a test notification to a channel."""
    config = load_config(ctx.obj["config_path"])
    _setup_logging(config.settings.log_level)

    from webtracker.notify.dispatcher import NotificationDispatcher
    from webtracker.state.store import StateStore

    with StateStore(config.settings.state_db) as store:
        dispatcher = NotificationDispatcher(config.notifications, store)

        async def _send():
            try:
                success = await dispatcher.send_test(channel, message)
                if success:
                    console.print(f"[green]Test notification sent to '{channel}'![/green]")
                else:
                    console.print(f"[red]Failed to send test notification to '{channel}'[/red]")
            finally:
                await dispatcher.close()

        asyncio.run(_send())


@notify_group.command("history")
@click.option("--tracker", "-t", default=None, help="Filter by tracker ID")
@click.option("--last", "-n", default=50, help="Number of entries to show")
@click.pass_context
def notify_history(ctx: click.Context, tracker: str | None, last: int) -> None:
    """View notification history."""
    config = load_config(ctx.obj["config_path"])
    from datetime import datetime

    from webtracker.state.store import StateStore

    with StateStore(config.settings.state_db) as store:
        entries = store.get_notification_history(tracker_id=tracker, limit=last)

        if not entries:
            console.print("[yellow]No notifications sent yet[/yellow]")
            return

        table = Table(title="Notification History")
        table.add_column("Time", style="dim")
        table.add_column("Tracker", style="cyan")
        table.add_column("Channel", style="yellow")
        table.add_column("Message", style="white")

        for entry in entries:
            ts = datetime.fromtimestamp(entry["sent_at"]).strftime("%Y-%m-%d %H:%M:%S")
            msg = entry["message"][:80] + "..." if len(entry["message"]) > 80 else entry["message"]
            table.add_row(ts, entry["tracker_id"], entry["channel"], msg)

        console.print(table)


# ── Auth Commands ────────────────────────────────────────


@cli.group("auth")
def auth_group() -> None:
    """Authentication management commands."""


@auth_group.command("setup")
@click.argument("profile_name")
@click.option("--url", default="https://www.google.com", help="Starting URL")
def auth_setup(profile_name: str, url: str) -> None:
    """Open a browser window for manual login. Close the browser when done."""
    from webtracker.auth.profiles import setup_profile

    console.print(f"[cyan]Opening browser for profile '{profile_name}'...[/cyan]")
    console.print("[yellow]Log in to the site, then close the browser window to save.[/yellow]")
    asyncio.run(setup_profile(profile_name, url))
    console.print(f"[green]Profile '{profile_name}' saved![/green]")


@auth_group.command("export-cookies")
@click.argument("profile_name")
@click.option("--output", "-o", required=True, help="Output file path")
@click.option("--url", default=None, help="Navigate to URL first to capture cookies")
def auth_export(profile_name: str, output: str, url: str | None) -> None:
    """Export cookies from a browser profile to a JSON file."""
    from webtracker.auth.profiles import export_cookies_from_profile

    async def _export():
        count = await export_cookies_from_profile(profile_name, output, url)
        console.print(f"[green]Exported {count} cookies to {output}[/green]")

    asyncio.run(_export())


@auth_group.command("list")
def auth_list() -> None:
    """List available browser profiles."""
    from webtracker.auth.profiles import list_profiles

    profiles = list_profiles()
    if not profiles:
        console.print("[yellow]No browser profiles found[/yellow]")
        return

    for p in profiles:
        console.print(f"  [cyan]{p}[/cyan]")


# ── Dashboard Command ────────────────────────────────────


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind address")
@click.option("--port", "-p", default=8080, help="Port")
@click.pass_context
def dashboard(ctx: click.Context, host: str, port: int) -> None:
    """Start the web dashboard for monitoring trackers."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Dashboard requires extra dependencies.[/red]")
        console.print("Install with: pip install webtracker[dashboard]")
        sys.exit(1)

    from webtracker.dashboard import create_app

    config = load_config(ctx.obj["config_path"])
    _setup_logging(config.settings.log_level)

    app = create_app(config)
    console.print(f"[green]Dashboard starting at http://{host}:{port}[/green]")
    uvicorn.run(app, host=host, port=port, log_level=config.settings.log_level)
