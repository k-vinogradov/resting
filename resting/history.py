from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Optional, TypeVar, Union

import aiohttp

T = TypeVar("T")


class History(Mapping):
    def __init__(self):
        self._responses: Dict[str, Optional[aiohttp.ClientResponse]] = {}
        self._labels: List[str] = []

    def __getitem__(self, key: Union[str, int]) -> Optional[aiohttp.ClientResponse]:
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

    def add(self, label: str):
        label = self._label(label)
        self._labels.append(label)
        self._responses[label] = None

    def store_current_response(self, response: aiohttp.ClientResponse):
        self._responses[self._labels[-1]] = response

    async def get_value_by_path(self, path: List[str]) -> Any:
        key, *path = path
        response: aiohttp.ClientResponse = get_by_key_or_index(self, key)
        if not response:
            raise ValueError(f"No response '{key}' found")
        match path:
            case ["headers", header]:
                return response.headers[header]
            case ["json", *rest]:
                return get_dict_value(rest, await response.json())

    def _label(self, prefix):
        if prefix not in self._labels:
            return prefix
        counter = 2
        while f"{prefix}{counter}" in self._labels:
            counter += 1
        return f"{prefix}{counter}"


def get_by_key_or_index(
    data: Mapping[Union[str, int], T],
    key: str,
) -> T:
    try:
        return data[int(key)]
    except ValueError:
        return data[key]


def get_dict_value(path: List[str], data: dict) -> Any:
    while path:
        key, *path = path
        data = get_by_key_or_index(data, key)
    return data
