import argparse
import asyncio
import logging
import sys
from enum import IntEnum

import yaml

from resting.errors import RestingError
from resting.output import VerboseLevel
from resting.script import Script
from resting.session import ClientSession

logger = logging.getLogger(__name__)


class Exit(IntEnum):
    SUCCESS = 0
    INVALID_SCRIPT = 1
    SCRIPT_FAILED = 2


def configure_logger(level: int):
    root_logger = logging.getLogger(__name__.split(".")[0])
    root_logger.addHandler(logging.StreamHandler())
    root_logger.setLevel(level)


def log_level(level: str):
    level = logging.getLevelName(level.upper())
    if isinstance(level, str) and level.startswith("Level "):
        raise ValueError(f"{level} is unknown")
    return level


async def run(script: Script, verbose_level: VerboseLevel) -> int:
    async with ClientSession(verbose_level=verbose_level) as session:
        try:
            await script.process(session)
        except RestingError as exception:
            logger.error(f"Script failed:\n  {exception}")
        except Exception as exception:
            logger.exception(f"Script failed:\n  {exception}")
        else:
            return Exit.SUCCESS
    return Exit.SCRIPT_FAILED


LOADERS = {"yaml/json": yaml.safe_load}


def main():
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
    parser.add_argument(
        "--log-level",
        type=log_level,
        default=logging.getLevelName(logging.ERROR).lower(),
        help="Console logger level",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    args = parser.parse_args()

    configure_logger(args.log_level)
    try:
        logger.info("Load script from %s", args.script.name)
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
