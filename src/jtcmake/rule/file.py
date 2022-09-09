from abc import ABC, abstractmethod
import os, time, hashlib, base64
from pathlib import PurePath, Path

from .memo.abc import IMemoAtom, ILazyMemoValue


class IFileBase(IMemoAtom):
    @property
    @abstractmethod
    def path(self):
        ...

    @abstractmethod
    def copy_with(self, path):
        ...

    # mixins
    @property
    def abspath(self):
        return Path(os.path.abspath(self.path))

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return type(other) == type(self) and self.abspath == other.abspath

    def __repr__(self):
        return f"{type(self).__name__}(path={repr(self.path)})"


class IFile(IFileBase):
    # Marker interface for (referencial) files
    # memo_value must be constant (must not be further overridden)
    @property
    def memo_value(self):
        return None


class IVFile(IFileBase):
    # Marker interface for value files
    ...


class File(IFile):
    def __init__(self, path):
        """
        Create an object representing a file to be used as an input to
        rules. Its modification time is checked when JTCMake determines
        whether to update the rules.

        Args:
            path (str|os.PathLike): path of the file
        """
        assert isinstance(path, (str, os.PathLike))
        self._path = Path(path)

    @property
    def path(self):
        return self._path

    def copy_with(self, path):
        return File(path)


class _ContentHash(ILazyMemoValue):
    def __init__(self, path):
        self.path = path

    def __call__(self):
        return get_hash(self.path)


class VFile(IVFile):
    def __init__(self, path):
        """
        Create an object representing a file to be used as an input to
        rules. This is for a value file: its content is checked when
        JTCMake determines whether to update the rules.

        Args:
            path (str|os.PathLike): path of the file
        """
        assert isinstance(path, (str, os.PathLike))
        self._path = Path(path)
        self._memo_value = _ContentHash(path)

    @property
    def path(self):
        return self._path

    @property
    def memo_value(self):
        return self._memo_value

    def copy_with(self, path):
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
