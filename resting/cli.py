import argparse
import asyncio
import logging
import sys
from enum import IntEnum

import yaml

from resting.errors import RestingError
from resting.script import Script
from resting.session import ClientSession
from resting.output import font

logger = logging.getLogger(__name__)


class Exit(IntEnum):
    SUCCESS = 0
    INVALID_SCRIPT = 1
    SCRIPT_FAILED = 2


class LogHandler(logging.StreamHandler):
    def format(self, record: logging.LogRecord) -> str:
        s = super().format(record)
        if self.stream.isatty():
            if record.levelno >= logging.ERROR:
                return font.red.bold(s)
            elif record.levelno == logging.WARNING:
                return font.yellow.bold(s)
        return s


def configure_logger(level: int):
    root_logger = logging.getLogger(__name__.split(".")[0])
    root_logger.addHandler(LogHandler())
    root_logger.setLevel(level)


def log_level(level: str):
    level = logging.getLevelName(level.upper())
    if isinstance(level, str) and level.startswith("Level "):
        raise ValueError(f"{level} is unknown")
    return level


async def run(script: Script, silent: bool) -> int:
    async with ClientSession(silent=silent) as session:
        try:
            await script.process(session)
        except RestingError as exception:
            logger.error(exception)
        except Exception as exception:
            logger.exception(exception)
        else:
            return Exit.SUCCESS
    if silent:
        await session.print_last_request()
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

    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        default=False,
        help="Do not print success request",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        type=log_level,
        default="warning",
        help="Console logger level",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    args = parser.parse_args()

    configure_logger(args.log_level)
    try:
        logger.info("Load script %s", args.script.name)
        script_config = LOADERS[args.loader](args.script)
        if not isinstance(script_config, dict):
            raise ValueError("Mapping structure is expected")
        script = Script(**script_config)
    except Exception as exception:
        logger.critical("Failed to load script: %s", exception)
        sys.exit(Exit.INVALID_SCRIPT)
    finally:
        args.script.close()
    sys.exit(asyncio.run(run(script, args.silent)))


if __name__ == "__main__":
    main()
