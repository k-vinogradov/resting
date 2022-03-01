from __future__ import annotations

from typing import Mapping, List, Any, TypeVar


T = TypeVar("T")


def get_item(
    data: Mapping[str | int, T],
    key: str,
) -> T:
    try:
        return data[int(key)]
    except ValueError:
        return data[key]


def get_dict_value(path: List[str], data: dict) -> Any:
    rest = path
    while rest:
        key, *rest = rest
        data = get_item(data, key)
    return data
