"""HTTP engine using httpx for lightweight page fetching."""

from __future__ import annotations

import httpx

from webtracker.auth.cookies import cookies_as_httpx_dict, load_cookies_file
from webtracker.config import AuthType, TrackerConfig
from webtracker.engine.base import Engine, FetchResult
from webtracker.engine.useragents import get_user_agent


class HttpEngine(Engine):
    """Fetches pages using HTTP requests (no JavaScript rendering)."""

    def __init__(self) -> None:
        # Clients keyed by proxy URL (None = no proxy)
        self._clients: dict[str | None, httpx.AsyncClient] = {}

    def _get_client(self, proxy: str | None) -> httpx.AsyncClient:
        if proxy not in self._clients:
            self._clients[proxy] = httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                proxy=proxy,
            )
        return self._clients[proxy]

    async def fetch(self, tracker: TrackerConfig) -> FetchResult:
        client = self._get_client(tracker.proxy)

        headers = {"User-Agent": get_user_agent(tracker)}
        headers.update(tracker.headers)

        cookies: dict[str, str] = {}
        if tracker.auth and tracker.auth.type == AuthType.COOKIES and tracker.auth.file:
            cookies = cookies_as_httpx_dict(load_cookies_file(tracker.auth.file))

        response = await client.get(tracker.url, headers=headers, cookies=cookies)
        response.raise_for_status()

        return FetchResult(
            html=response.text,
            status_code=response.status_code,
            url=str(response.url),
        )

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
