from typing import Optional


class RestingError(Exception):
    pass


class InvalidPath(RestingError):
    def __init__(self, path, item: Optional[str] = None):
        self.path = path
        self.item = item

    def __str__(self):
        details = ""
        if self.item:
            details = f": unknown item {self.item!r}"
        return f"invalid path {self.path!r}{details}"
