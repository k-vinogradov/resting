from __future__ import annotations

import logging
from sys import stdout
from typing import Optional, TextIO

import aiohttp
from aiohttp.connector import Connection

from resting.history import History
from resting.output import request_printer, response_printer, VerboseLevel

logger = logging.getLogger(__name__)


class TCPConnector(aiohttp.TCPConnector):
    def __init__(self, *args, print_request, **kwargs):
        super().__init__(*args, **kwargs)
        self._print_request = print_request

    async def connect(self, req: aiohttp.ClientRequest, *args, **kwargs) -> Connection:
        await self._print_request(req)
        return await super().connect(req, *args, **kwargs)


class ClientSession(aiohttp.ClientSession):
    def __init__(
        self,
        *args,
        verbose_level: int = VerboseLevel.FULL,
        print_stream: TextIO = stdout,
        connector: Optional[aiohttp.BaseConnector] = None,
        **kwargs,
    ):
        history = History()
        super().__init__(
            *args,
            connector=TCPConnector(
                loop=aiohttp.helpers.get_running_loop(),
                print_request=request_printer(print_stream, verbose_level),
            ),
            **kwargs,
        )
        self._print_response = response_printer(print_stream, verbose_level)
        self._history = history

    async def __aenter__(self) -> ClientSession:
        return await super().__aenter__()  # type: ClientSession

    @property
    def history(self):
        return self._history

    async def _request(
        self, *args, label: str = "unnamed", **kwargs
    ) -> aiohttp.ClientResponse:
        self._history.add(label)
        response = await super()._request(*args, **kwargs)
        await self._print_response(response)
        await self.history.store_current_response(response)
        return response
