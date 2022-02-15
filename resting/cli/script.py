import argparse
import asyncio
import logging
import re
import sys
from enum import IntEnum
from typing import Any, Callable, List, Optional, Tuple

import yaml
from multidict import CIMultiDict
from pydantic import BaseModel, Field

from resting.history import get_dict_value
from resting.output import VerboseLevel
from resting.session import ClientSession

logger = logging.getLogger(__name__)


JSONData = list | dict

SUBSTITUTE = re.compile(r"{(?P<path>[\w.-]+)}")


class Exit(IntEnum):
    SUCCESS = 0
    INVALID_SCRIPT = 1
    SCRIPT_FAILED = 2


class Header(BaseModel):
    name: str
    value: str

    async def get(self, converter: Callable) -> Tuple[str, str]:
        return await converter(self.name), await converter(self.value)


class Step(BaseModel):
    label: str = "unnamed_request"
    method: str
    url: str
    headers: Optional[List[Header]] = None
    json_data: Optional[JSONData] = Field(None, alias="json")

    async def get_method(self, converter: Callable) -> str:
        return await converter(self.method)

    async def get_url(self, converter: Callable) -> str:
        return await converter(self.url)

    async def get_headers(self, converter: Callable) -> Optional[CIMultiDict]:
        if not self.headers:
            return None
        headers: CIMultiDict = CIMultiDict()
        for header in self.headers:
            name, value = await header.get(converter)
            headers[name] = value
        return headers

    async def get_json_data(self, converter: Callable) -> Optional[JSONData]:
        return await converter(self.json_data)

    async def process(self, session: ClientSession, converter: Callable):
        request = session.request(
            await self.get_method(converter),
            await self.get_url(converter),
            label=self.label,
            headers=await self.get_headers(converter),
            json=await self.get_json_data(converter),
        )
        async with request as _:
            pass


class Script(BaseModel):
    environment: Optional[dict] = None
    steps: List[Step]

    async def process(self, session: ClientSession) -> int:
        converter = create_converter(session, self.environment)
        for number, step in enumerate(self.steps, 1):
            try:
                await step.process(session, converter)
            except Exception as exception:
                logger.error(
                    "'%s' step (%s of %s) failed: %s",
                    step.label,
                    number,
                    len(self.steps),
                    exception,
                )
                return Exit.SCRIPT_FAILED
        return Exit.SUCCESS


def create_converter(session: ClientSession, environment: Optional[dict]) -> Callable:
    async def convert(value: Any):
        if isinstance(value, dict):
            return {await convert(k): await convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return map(convert, value)
        if isinstance(value, str):
            substitutes = []
            for path in SUBSTITUTE.findall(value):
                substitutes.append((f"{{{path}}}", await substitute(path)))
            for sub, rep in substitutes:
                value = value.replace(sub, rep)
            return value
        return value

    async def substitute(path):
        match path.split("."):
            case ["environment", *rest]:
                if not environment:
                    raise ValueError("Empty environment")
                return get_dict_value(rest, environment)
            case ["history", *rest]:
                return await session.history.get_value_by_path(rest)
        raise ValueError(f"invalid substitute {path!r}")

    return convert


async def run(script: Script, verbose_level: VerboseLevel) -> int:
    async with ClientSession(verbose_level=verbose_level) as session:
        return await script.process(session)


LOADERS = {"yaml/json": yaml.safe_load}


def main():
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    parser = argparse.ArgumentParser(description="Run pre-defined script")
    parser.add_argument(
        "script",
        metavar="SCRIPT",
        type=argparse.FileType("r"),
        help="Path to script file",
    )

    loader_names = list(LOADERS.keys())
    parser.add_argument(
        "--loader",
        type=str,
        choices=loader_names,
        default=loader_names[0],
        help=f"Script file loader ('{loader_names[0]}' is default)",
    )

    verbose_levels = {
        item.value: item.name.lower().replace("_", " ") for item in VerboseLevel
    }
    levels_description = ", ".join(
        f"{key} - {value}" for key, value in verbose_levels.items()
    )
    parser.add_argument(
        "--verbose",
        type=int,
        choices=verbose_levels.keys(),
        default=VerboseLevel.FULL,
        help=f"Requests/responses info verbose level ({levels_description}, "
        f"default is {VerboseLevel.FULL})",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    args = parser.parse_args()

    try:
        script_config = LOADERS[args.loader](args.script)
        if not isinstance(script_config, dict):
            raise ValueError("Mapping structure is expected")
        script = Script(**script_config)
    except Exception as exception:
        logger.critical("Failed to load script: %s", exception)
        sys.exit(Exit.INVALID_SCRIPT)
    finally:
        args.script.close()
    sys.exit(asyncio.run(run(script, args.verbose)))


if __name__ == "__main__":
    main()
