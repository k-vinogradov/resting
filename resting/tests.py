from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from pydantic import BaseModel

from resting.errors import RestingError
from resting.session import ClientSession

logger = logging.getLogger(__name__)


class TestError(RestingError):
    def __init__(self, test: BaseTest, message: str):
        self.test = test
        self.message = message

    def __str__(self):
        return f"test {self.test.name!r} failed: {self.message}"


class BaseTest(ABC, BaseModel):
    async def run(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        try:
            await self._assert(session, converter, environment)
        except AssertionError as exception:
            raise TestError(self, str(exception))

    @abstractmethod
    async def _assert(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        pass

    @property
    def name(self):
        return list(self.__fields_set__)[0]


class Sleep(BaseTest):
    sleep: float | int | str

    async def _assert(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        delay = float(await converter(self.sleep))
        logger.debug(f"Waiting for {delay} sec")
        await asyncio.sleep(delay)


class Status(BaseTest):
    status: int | str

    async def _assert(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        status = session.history.last.status
        expected = int(await converter(self.status))
        assert status == expected, f"response status {status} but {expected} expected"


class UpdateEnvironment(BaseTest):
    update_environment: dict

    async def _assert(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        for key, value in self.update_environment.items():
            environment[await converter(key)] = await converter(value)


Test = Sleep | Status | UpdateEnvironment
