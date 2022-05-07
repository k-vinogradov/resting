from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from resting import ClientSession

logger = logging.getLogger(__name__)


class BaseTest(ABC, BaseModel):
    @abstractmethod
    async def run(
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

    async def run(
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

    async def run(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        assert session.history.last, "no last request found"
        status = session.history.last.status
        expected = int(await converter(self.status))
        assert status == expected, f"response status {status} but {expected} expected"


class Equal(BaseTest):
    eq: list

    async def run(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        assert len(self.eq) == 2, "only two items can be compared"
        a, b = [await converter(value) for value in self.eq]
        # TODO: readable diff output
        assert a == b, f"items are not equal:\n{a}\n{b}"


class UpdateEnvironment(BaseTest):
    update_environment: dict

    async def run(
        self,
        session: ClientSession,
        converter: Callable[[Any], Any],
        environment: Dict[str, Any],
    ):
        for key, value in self.update_environment.items():
            environment[await converter(key)] = await converter(value)


class Print(BaseTest):
    print: str

    async def run(self, session, converter, environment):
        logger.warning(await converter(self.print))


Test = Sleep | Status | UpdateEnvironment | Print | Equal
