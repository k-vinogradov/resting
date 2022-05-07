from __future__ import annotations

import re
import logging
from datetime import date, datetime
from typing import Callable, Dict, Optional, List, Any

from multidict import CIMultiDict
from pydantic import BaseModel, Field

from resting import errors
from resting.utils import get_dict_value
from resting.session import ClientSession
from resting.tests import Test

JSONData = list | dict
SUBSTITUTE = re.compile(r"{(?P<path>[\w.-]+)}")

logger = logging.getLogger(__name__)


class Step(BaseModel):
    label: str = "unnamed"
    method: str
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    json_data: Optional[JSONData] = Field(None, alias="json")
    tests: List[Test] = Field(default_factory=list)

    async def get_method(self, converter: Callable) -> str:
        return await converter(self.method)

    async def get_url(self, converter: Callable) -> str:
        return await converter(self.url)

    async def get_headers(self, converter: Callable) -> Optional[CIMultiDict]:
        return CIMultiDict(
            [
                (await converter(key), await converter(value))
                for key, value in self.headers.items()
            ]
        )

    async def get_json_data(self, converter: Callable) -> Optional[JSONData]:
        return await converter(self.json_data)

    async def process(
        self, session: ClientSession, converter: Callable, environment: Dict[str, Any]
    ):
        request = session.request(
            method=await self.get_method(converter),
            url=await self.get_url(converter),
            label=self.label,
            headers=await self.get_headers(converter),
            json=await self.get_json_data(converter),
        )
        async with request as _:
            for number, test in enumerate(self.tests, start=1):
                logger.info(
                    "Check test %s of %s: %r", number, len(self.tests), test.name
                )
                try:
                    await test.run(session, converter, environment)
                except AssertionError as exc:
                    raise errors.TestError(test=test, step=self) from exc


class Script(BaseModel):
    environment: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step]

    async def process(self, session: ClientSession):
        converter = create_converter(session, self.environment)
        logger.info("Start script processing")
        for step in self.steps:
            logger.info("Run step %r", step.label)
            try:
                await step.process(session, converter, self.environment)
            except errors.RestingError as exception:
                raise errors.FailedStepError(step=step, script=self) from exception
            except Exception as exception:
                logger.exception("Unexpected error on script processing")
                raise errors.FailedStepError(step=step, script=self) from exception
        logger.info("Script processing complete")


def create_converter(
    session: ClientSession, environment: Dict[str, Any]
) -> Callable[[Any], Any]:
    async def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {await convert(k): await convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [await convert(item) for item in value]
        if isinstance(value, str):
            if value.startswith("_path_:"):
                return await substitute(value[len("_path_:") :])
            substitutes = []
            for path in SUBSTITUTE.findall(value):
                substitutes.append((f"{{{path}}}", await substitute(path)))
            for sub, rep in substitutes:
                value = value.replace(sub, str(rep))
            return value
        if isinstance(value, datetime | date):
            return value.isoformat()
        return value

    async def substitute(path):
        match path.split("."):
            case ["environment", *rest]:
                try:
                    return get_dict_value(rest, environment)
                except LookupError as exception:
                    raise errors.InvalidPath(path, exception.args[0])
            case ["history", *rest]:
                return await session.history.get_value_by_path(rest)
        raise errors.InvalidPath(path)

    return convert
