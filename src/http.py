import asyncio
import json as json_module
from dataclasses import dataclass

from aiohttp import ClientSession, ClientTimeout

from src.ansi import ANSI
from src.constants import (
    ALLOW_REDIRECTS,
    REQUEST_MAX_TRIES,
    REQUEST_SSL,
    REQUEST_TIMEOUT,
    SLEEP_BETWEEN_REQUESTS,
)
from src.exceptions import AccountBanned, InvalidCookie
from src.utils import log


@dataclass(slots=True)
class HttpResponse:
    status: int
    headers: dict
    text: str

    def json(self) -> dict:
        return json_module.loads(self.text)

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


class HttpClient:
    def __init__(
        self,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ) -> None:
        self._default_headers = headers or {}
        self._default_cookies = cookies or {}
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "HttpClient":
        await self.open()
        return self

    async def __aexit__(self, *_args) -> None:
        await self.close()

    async def open(self) -> None:
        if self._session is not None and not self._session.closed:
            return

        self._session = ClientSession(
            headers=self._default_headers,
            cookies=self._default_cookies,
            timeout=ClientTimeout(total=REQUEST_TIMEOUT),
        )

    async def close(self) -> None:
        if self._session is None:
            return

        await self._session.close()
        self._session = None

    async def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        json: dict | None = None,
        allow_redirects: bool = ALLOW_REDIRECTS,
        allowed_statuses: set[int] | None = None,
    ) -> HttpResponse:
        return await self._request(
            "GET",
            url,
            params=params,
            data=data,
            headers=headers,
            json=json,
            allow_redirects=allow_redirects,
            allowed_statuses=allowed_statuses or {200},
        )

    async def post(
        self,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        json: dict | None = None,
        allow_redirects: bool = ALLOW_REDIRECTS,
        allowed_statuses: set[int] | None = None,
    ) -> HttpResponse:
        return await self._request(
            "POST",
            url,
            params=params,
            data=data,
            headers=headers,
            json=json,
            allow_redirects=allow_redirects,
            allowed_statuses=allowed_statuses or {200},
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        json: dict | None = None,
        allow_redirects: bool,
        allowed_statuses: set[int],
    ) -> HttpResponse:
        await self.open()
        last_error: Exception | None = None
        last_status: int | None = None
        last_text = ""

        for _ in range(REQUEST_MAX_TRIES):
            try:
                assert self._session is not None

                async with self._session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    json=json,
                    allow_redirects=allow_redirects,
                    ssl=REQUEST_SSL,
                ) as response:
                    text = await response.text()
                    payload = HttpResponse(
                        status=response.status,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        text=text,
                    )

                    if payload.status in allowed_statuses:
                        return payload

                    if payload.status == 302 and payload.header("location") == "/not-approved":
                        raise AccountBanned

                    if payload.status in {302, 401}:
                        raise InvalidCookie

                    last_status = payload.status
                    last_text = payload.text
                    log(f"{method} | Failed with unexpected status code: {payload.status}", ANSI.RED)
                    if payload.text:
                        log(f"{method} | {payload.text}", ANSI.RED)
            except (InvalidCookie, AccountBanned):
                raise
            except Exception as error:
                last_error = error
                log(f"{method} | Failed request ({type(error).__name__}): {error!r}", ANSI.RED)

            await asyncio.sleep(SLEEP_BETWEEN_REQUESTS)

        if last_error is not None:
            raise RuntimeError(f"{method} {url} failed: {last_error}") from last_error

        raise RuntimeError(
            f"{method} {url} failed with status {last_status}. Response: {last_text}"
        )
