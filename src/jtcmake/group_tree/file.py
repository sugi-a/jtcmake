from __future__ import annotations
import os, sys
from abc import abstractmethod
import hashlib, base64
import pathlib
from typing import Any, Dict, Tuple

from ..utils.strpath import StrOrPath
from ..memo.abc import IMemoAtom, ILazyMemoValue


if sys.platform == "win32":
    _Path = pathlib.WindowsPath
else:
    _Path = pathlib.PosixPath


class IFile(_Path, IMemoAtom):
    @abstractmethod
    def copy_with(self, path: StrOrPath) -> IFile:
        ...


class File(IFile):
    """
    An instance of this class represents a file, which can be an input or
    output of rules.

    When used as an input, on judging whether the rule must be updated,
    its modification time is compared to the modification time of the
    output files.
    If any of the output files is older than the input, the rule must be
    updated.
    """

    def copy_with(self, path: StrOrPath) -> File:
        return File(path)

    @property
    def memo_value(self) -> Any:
        return None


class _ContentHash(ILazyMemoValue):
    __slots__ = ["path"]

    def __init__(self, path: StrOrPath):
        self.path = path

    def __call__(self) -> str:
        return get_hash(self.path)


class VFile(IFile):
    """
    An instance of this class represents a value file, which can be
    an input or output of rules.

    When used as an input, on judging whether the rule must be updated,
    its modification time is compared to the modification time of the
    output files.
    If any of the output files is older than the input, the rule must be
    updated.
    """

    __slots__ = ["_memo_value"]

    def __init__(self, path: StrOrPath):
        self._memo_value = _ContentHash(path)

    @property
    def memo_value(self) -> Any:
        return self._memo_value

    def copy_with(self, path: StrOrPath) -> VFile:
        return VFile(path)


_hash_cache: Dict[str, Tuple[float, str]] = {}


def get_hash(fname: StrOrPath) -> str:
    fname = os.path.realpath(fname)

    if fname in _hash_cache:
        if os.path.getmtime(fname) == _hash_cache[fname][0]:
            return _hash_cache[fname][1]

    mtime = os.path.getmtime(fname)

    with open(fname, "rb") as f:
        res = base64.b64encode(hashlib.md5(f.read()).digest()).decode()

    _hash_cache[os.path.abspath(fname)] = (mtime, res)

    return res
