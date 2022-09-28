import os
from abc import ABC, abstractmethod
import os, time, hashlib, base64
from pathlib import Path, WindowsPath, PosixPath

from .memo.abc import IMemoAtom, ILazyMemoValue

_Path = WindowsPath if os.name == "nt" else PosixPath


class IFile(_Path, IMemoAtom):
    @abstractmethod
    def replace(self, path):
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

    def replace(self, path):
        return File(path)

    @property
    def memo_value(self):
        return None


class _ContentHash(ILazyMemoValue):
    def __init__(self, path):
        self.path = path

    def __call__(self):
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

    def __init__(self, path):
        self._memo_value = _ContentHash(path)

    @property
    def memo_value(self):
        return self._memo_value

    def replace(self, path):
        return VFile(path)


_hash_cache = {}


def get_hash(fname):
    fname = os.path.realpath(fname)

    if fname in _hash_cache:
        if os.path.getmtime(fname) == _hash_cache[fname][0]:
            return _hash_cache[fname][1]

    mtime = os.path.getmtime(fname)

    with open(fname, "rb") as f:
        res = base64.b64encode(hashlib.md5(f.read()).digest()).decode()

    _hash_cache[fname] = (mtime, res)

    return res
