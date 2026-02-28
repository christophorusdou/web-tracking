"""HTTP engine using httpx for lightweight page fetching."""

from __future__ import annotations

import httpx

from webtracker.auth.cookies import cookies_as_httpx_dict, load_cookies_file
from webtracker.config import AuthType, TrackerConfig
from webtracker.engine.base import Engine, FetchResult

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HttpEngine(Engine):
    """Fetches pages using HTTP requests (no JavaScript rendering)."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    async def fetch(self, tracker: TrackerConfig) -> FetchResult:
        client = await self._get_client()

        headers = {"User-Agent": _DEFAULT_USER_AGENT}
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
        if self._client:
            await self._client.aclose()
            self._client = None
