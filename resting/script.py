from __future__ import annotations

import re
import logging
from typing import Callable, Dict, Tuple, Optional, List, Any

from multidict import CIMultiDict
from pydantic import BaseModel, Field

from resting.errors import InvalidPath, RestingError
from resting.utils import get_dict_value
from resting.session import ClientSession
from resting.tests import Test

JSONData = list | dict
SUBSTITUTE = re.compile(r"{(?P<path>[\w.-]+)}")

logger = logging.getLogger(__name__)


class FailedStepError(RestingError):
    def __init__(self, step: Step, failed_step: int, total: int):
        self.step = step
        self.failed_step = failed_step
        self.total = total

    def __str__(self):
        cause = f":\n  {self.__cause__}" if self.__cause__ else ""
        return (
            f"step {self.failed_step} of {self.total} {self.step.label!r} failed{cause}"
        )


class EmptyEnvironment(InvalidPath):
    message = "empty environment"

    def __str__(self):
        return self.message


class Header(BaseModel):
    name: str
    value: str

    async def get(self, converter: Callable) -> Tuple[str, str]:
        return await converter(self.name), await converter(self.value)


class Step(BaseModel):
    label: str = "unnamed"
    method: str
    url: str
    headers: List[Header] = Field(default_factory=list)
    json_data: Optional[JSONData] = Field(None, alias="json")
    tests: List[Test] = Field(default_factory=list)

    async def get_method(self, converter: Callable) -> str:
        return await converter(self.method)

    async def get_url(self, converter: Callable) -> str:
        return await converter(self.url)

    async def get_headers(self, converter: Callable) -> Optional[CIMultiDict]:
        return CIMultiDict([await header.get(converter) for header in self.headers])

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
                logger.debug(
                    "Run test '%s' (%s of %s)", test.name, number, len(self.tests)
                )
                await test.run(session, converter, environment)


class Script(BaseModel):
    environment: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step]

    async def process(self, session: ClientSession):
        converter = create_converter(session, self.environment)
        logger.info("Start script processing")
        for number, step in enumerate(self.steps, 1):
            logger.info("%s of %s: %s", number, len(self.steps), step.label)
            try:
                await step.process(session, converter, self.environment)
            except RestingError as exception:
                raise FailedStepError(
                    step=step, failed_step=number, total=len(self.steps)
                ) from exception
            except Exception as exception:
                logger.exception("Unexpected error on script processing")
                raise FailedStepError(
                    step=step, failed_step=number, total=len(self.steps)
                ) from exception
        logger.info("Script processing complete")


def create_converter(
    session: ClientSession, environment: Dict[str, Any]
) -> Callable[[Any], Any]:
    async def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {await convert(k): await convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return map(convert, value)
        if isinstance(value, str):
            substitutes = []
            for path in SUBSTITUTE.findall(value):
                substitutes.append((f"{{{path}}}", await substitute(path)))
            for sub, rep in substitutes:
                value = value.replace(sub, str(rep))
            return value
        return value

    async def substitute(path):
        match path.split("."):
            case ["environment", *rest]:
                try:
                    return get_dict_value(rest, environment)
                except LookupError as exception:
                    raise InvalidPath(path, exception.args[0])
            case ["history", *rest]:
                return await session.history.get_value_by_path(rest)
        raise InvalidPath(path)

    return convert
