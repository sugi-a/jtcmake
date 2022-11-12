from __future__ import annotations
import os, sys
from abc import ABCMeta, abstractmethod
import hashlib, base64
import pathlib
from typing import Dict, Tuple

from ..utils.strpath import StrOrPath
from ..memo.abc import IMemoAtom, ILazyMemoValue


if sys.platform == "win32":
    _Path = pathlib.WindowsPath
else:
    _Path = pathlib.PosixPath


class IFile(_Path, IMemoAtom, metaclass=ABCMeta):
    """
    Abstract base class to represent a file object.
    """

    """
    For implementors of this ABC:
        It is highly recommended not to have variable properties (public or
        private) in the new class because the default implementations of the
        generative methods of Path (absolute(), resolve(), etc) create new
        instance without copying subclasses' variable properties.
    """
    @abstractmethod
    def is_value_file(self) -> bool:
        ...

    def __eq__(self, other: object) -> bool:
        ts, to = type(self), type(other)
        if issubclass(to, ts) or issubclass(ts, to):
            return super().__eq__(other)
        else:
            return False


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
    @property
    def memo_value(self) -> object:
        return None

    def is_value_file(self) -> bool:
        return False


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
    def is_value_file(self) -> bool:
        return True

    @property
    def memo_value(self) -> object:
        return _ContentHash(self)


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
