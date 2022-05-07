"""Requests output"""
from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional, TYPE_CHECKING

import aiohttp
from aiohttp import hdrs, Payload
from aiohttp.abc import AbstractStreamWriter
from pygments import highlight, lexers, formatters

if TYPE_CHECKING:
    from aiohttp.http_writer import HttpVersion
    from multidict import CIMultiDict
    from typing import Dict, List, Mapping, Optional, TextIO
    from yarl import URL

    from resting.session import RequestInfo


class Color:
    __slots__ = (
        "purple",
        "cyan",
        "darkcyan",
        "blue",
        "green",
        "yellow",
        "red",
        "_color",
        "_bold",
        "_underline",
    )
    _colors = {
        "purple": "\033[95m",
        "cyan": "\033[96m",
        "darkcyan": "\033[36m",
        "blue": "\033[94m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
    }
    _styles = {"bold": "\033[1m", "underline": "\033[4m"}
    _end = "\033[0m"

    def __init__(
        self,
        color: str = "",
        bold: str = "",
        underline: str = "",
    ):
        self._color, self._bold, self._underline = color, bold, underline

    @property
    def bold(self):
        return Color(self._color, self._styles["bold"], self._underline)

    @property
    def underline(self):
        return Color(self._color, self._bold, self._styles["underline"])

    def __getattr__(self, item):
        if item not in self._colors:
            raise AttributeError(item)
        return Color(self._colors[item], self._bold, self._underline)

    def __call__(self, text: str) -> str:
        prefix = "".join((self._color, self._bold, self._underline))
        suffix = prefix and self._end
        return f"{prefix}{text}{suffix}"


font = Color()

success = font.bold.green
redirect = font.bold.blue
error = font.bold.red

methods = {
    hdrs.METH_CONNECT: font.bold.green,
    hdrs.METH_HEAD: font.bold.green,
    hdrs.METH_OPTIONS: font.bold.green,
    hdrs.METH_TRACE: font.bold.green,
    hdrs.METH_GET: font.bold.green,
    hdrs.METH_PATCH: font.bold.yellow,
    hdrs.METH_POST: font.bold.yellow,
    hdrs.METH_PUT: font.bold.yellow,
    hdrs.METH_DELETE: font.bold.red,
}


class StreamWriter(AbstractStreamWriter):
    def __init__(self):
        self._data = []

    @property
    def data(self) -> bytes:
        return b"".join(self._data)

    async def write(self, chunk: bytes) -> None:
        self._data.append(chunk)

    async def write_eof(self, chunk: bytes = b"") -> None:
        raise NotImplementedError

    async def drain(self) -> None:
        raise NotImplementedError

    def enable_compression(self, encoding: str = "deflate") -> None:
        raise NotImplementedError

    def enable_chunking(self) -> None:
        raise NotImplementedError

    async def write_headers(self, status_line: str, headers: CIMultiDict[str]) -> None:
        raise NotImplementedError


def print_json_data(fd: TextIO, data: Dict | List):
    json_text = json.dumps(data, sort_keys=True, indent=2)
    if fd.isatty():
        formatter = formatters.TerminalFormatter()
        json_text = highlight(json_text, lexers.JsonLexer(), formatter)
    fd.write(f"{json_text}")


def print_json(fd: TextIO, json_text: str | bytes):
    print_json_data(fd, json.loads(json_text))


def print_html(fd: TextIO, html_text: str):
    if fd.isatty():
        formatter = formatters.TerminalFormatter()
        html_text = highlight(html_text, lexers.HtmlLexer(), formatter)
    fd.write(f"{html_text}\n")


def print_payload(fd: TextIO, context_type: str, payload: str | bytes):
    if not payload:
        return
    if "application/json" in context_type:
        print_json(fd, payload)
    elif "text/html" in context_type and isinstance(payload, str):
        print_html(fd, payload)
    else:
        fd.write(f"{payload}\n")  # type: ignore


def print_headers(fd: TextIO, headers: Mapping, strip: Optional[int] = None):
    key_font = font.cyan if fd.isatty() else font
    for key, value in sorted(headers.items()):
        value = str(value)
        if strip and len(value) > strip:
            value = f"{value[:strip + 1]}..."
        fd.write(f"{key_font(key)}: {value}\n")


def print_response_status(fd: TextIO, version: HttpVersion, status: int, reason: str):
    protocol_text = f"HTTP/{version.major}.{version.minor}"
    status_text = f"{status} {reason}"
    if fd.isatty():
        protocol_text = font.bold(protocol_text)
        if status < 300:
            status_text = success(status_text)
        elif status < 400:
            status_text = redirect(status_text)
        else:
            status_text = error(status_text)
    fd.write(f"{protocol_text} {status_text}\n")


def print_request_status(fd: TextIO, version: HttpVersion, method: str, url: URL | str):
    info_text = f"{url} HTTP/{version.major}.{version.minor}"
    if fd.isatty():
        info_text = font.bold(info_text)
        method = methods[method](method)
    fd.write(f"{method} {info_text}\n")


async def print_request(request: aiohttp.ClientRequest, fd: TextIO):
    fd.write("\n")
    print_request_status(fd, request.version, request.method, request.url)
    print_headers(fd, request.headers)
    fd.write("\n")
    body = request.body
    content_type = "application/octet-stream"
    if isinstance(body, Payload):
        content_type = body.content_type
        writer = StreamWriter()
        await body.write(writer)
        body = writer.data
    print_payload(fd, content_type, body)
    fd.write("\n")


async def print_response(response: aiohttp.ClientResponse, fd: TextIO):
    fd.write("\n")
    print_response_status(fd, response.version, response.status, response.reason)  # type: ignore
    print_headers(fd, response.headers)
    fd.write("\n")
    print_payload(fd, response.content_type, await response.text())
    fd.write("\n")


def create_printer(fd: TextIO) -> Callable[[RequestInfo], Awaitable[None]]:
    async def print_(request_info: RequestInfo):
        if request_info.request:
            await print_request(request_info.request, fd)
        if request_info.response:
            await print_response(request_info.response, fd)

    return print_
