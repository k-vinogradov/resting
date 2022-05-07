from __future__ import annotations

from dataclasses import dataclass
from sys import stdout
from typing import Optional

import aiohttp
from aiohttp.connector import Connection

from resting.history import History
from resting.output import create_printer


@dataclass
class RequestInfo:
    label: str
    request: Optional[aiohttp.ClientRequest] = None
    response: Optional[aiohttp.ClientResponse] = None


class TCPConnector(aiohttp.TCPConnector):
    def __init__(self, *args, session: ClientSession, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = session

    async def connect(self, req: aiohttp.ClientRequest, *args, **kwargs) -> Connection:
        self._session.last.request = req  # type: ignore
        return await super().connect(req, *args, **kwargs)


class ClientSession(aiohttp.ClientSession):
    last: Optional[RequestInfo] = None

    def __init__(
        self,
        *args,
        printer: Optional[Callable[[RequestInfo], Awaitable[None]]] = None,
        silent: bool = False,
        **kwargs,
    ):
        kwargs["connector"] = TCPConnector(
            loop=aiohttp.helpers.get_running_loop(), session=self
        )
        super().__init__(*args, **kwargs)
        self.history = History()
        self._print = printer or create_printer(stdout)
        self.silent = silent

    async def print_last_request(self):
        if self.last:
            await self._print(self.last)

    async def __aenter__(self) -> ClientSession:
        return await super().__aenter__()  # type: ignore

    async def _request(
        self, *args, label: str = "unnamed", **kwargs
    ) -> aiohttp.ClientResponse:
        self.last = RequestInfo(label=label)
        try:
            self.last.response = await super()._request(*args, **kwargs)
        finally:
            if not self.silent:
                await self.print_last_request()
        await self.history.add(label, self.last.response)
        return self.last.response
