from abc import ABC, abstractmethod
import os, time, hashlib, base64
from pathlib import PurePath, Path

from ..core.rule import IRule
from .memo.abc import IMemoAtom, ILazyMemoValue

class IFile(IMemoAtom):
    @property
    @abstractmethod
    def path(self): ...

    @property
    @abstractmethod
    def abspath(self): ...


class IVFile(IMemoAtom):
    @abstractmethod
    def get_hash(self): ...


class File(IFile):
    def __init__(self, path):
        assert isinstance(path, (str, os.PathLike))
        self._path = Path(path)

    @property
    def path(self):
        return self._path

    @property
    def abspath(self):
        return Path(os.path.abspath(self._path))

    def __hash__(self):
        return hash(self._path)

    def __eq__(self, other):
        return type(other) == type(self) and self._path == other._path

    def __repr__(self):
        return f'{type(self).__name__}(path={repr(self.path)})'

    @property
    def memo_value(self):
        return None


class VFile(IVFile, File):
    class _ContentHash(ILazyMemoValue):
        def __init__(self, path):
            self.path = path

        def __call__(self):
            return get_hash(self.path)


    def _clean(self):
        try:
            os.remove(self._path)
            os.remove(self.metadata_fname)
        except:
            pass

    def get_hash(self):
        return get_hash(self.path)


    @property
    def memo_value(self):
        return VFile._ContentHash(self.path)
        

_hash_cache = {}

def get_hash(fname):
    fname = os.path.realpath(fname)

    if fname in _hash_cache:
        if os.path.getmtime(fname) == _hash_cache[fname][0]:
            return _hash_cache[fname][1]

    mtime = os.path.getmtime(fname)

    with open(fname, 'rb') as f:
        res = base64.b64encode(hashlib.md5(f.read()).digest()).decode()

    _hash_cache[fname] = (mtime, res)

    return res
