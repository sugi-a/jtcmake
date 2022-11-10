from __future__ import annotations
from os import PathLike, fspath
from typing import Union
from typing_extensions import TypeAlias

StrOrPath: TypeAlias = "Union[str, PathLike[str]]"


def fspath2str(p: object) -> str:
    if isinstance(p, str):
        return p
    elif isinstance(p, PathLike):
        s = fspath(p)  # pyright: ignore [reportUnknownVariableType]
        if isinstance(s, str):
            return s
        elif isinstance(s, bytes):
            raise TypeError(f"bytes path is not supported. (given {s})")

    raise TypeError(f"Invalid path {p}")
