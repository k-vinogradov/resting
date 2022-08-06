from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Mapping, Optional

import aiohttp

from resting.utils import get_item, get_dict_value


RESERVED_LABELS = ("last",)

logger = logging.getLogger(__name__)


class History(Mapping):
    def __init__(self):
        self._responses: Dict[str, Optional[aiohttp.ClientResponse]] = {}
        self._labels: List[str] = []

    def __getitem__(self, key: str | int) -> Optional[aiohttp.ClientResponse]:
        if key == "last":
            return self.last
        if isinstance(key, int):
            key = self._labels[key]
        return self._responses[key]

    def __len__(self) -> int:
        return len(self._labels)

    def __iter__(self) -> Iterator[str]:
        return self._responses.__iter__()

    @property
    def last(self) -> Optional[aiohttp.ClientResponse]:
        return self[-1]

    @property
    def last_label(self) -> Optional[str]:  # type: ignore
        if self._labels:
            return self._labels[-1]

    async def add(self, label: str, response: aiohttp.ClientResponse):
        try:
            int(label)
            raise ValueError(f"label mustn't contain integer: {label!r}")
        except ValueError:
            pass
        if label in RESERVED_LABELS:
            raise ValueError(f"{label!r} is reserved label")
        label = self._label(label)
        self._labels.append(label)
        logger.debug(
            "Payload from %s %s received: %s bytes",
            response.request_info.method,
            response.request_info.url,
            len(await response.read()),
        )
        self._responses[label] = response

    async def get_value_by_path(self, path: List[str]) -> Any:
        key, *path = path
        response: aiohttp.ClientResponse = get_item(self, key)
        if not response:
            raise ValueError(f"No response '{key}' found")
        match path:
            case ["headers", header]:
                return response.headers[header]
            case ["cookies", name]:
                return response.cookies[name].value
            case ["json", *rest]:
                return get_dict_value(rest, await response.json())
            case ["status"]:
                return response.status
            case ["reason"]:
                return response.reason

    def _label(self, prefix):
        if prefix not in self._labels:
            return prefix
        counter = 2
        while f"{prefix}{counter}" in self._labels:
            counter += 1
        return f"{prefix}{counter}"
