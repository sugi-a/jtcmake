from abc import ABC, abstractmethod
from typing import Optional, Union
import os, time, hashlib, base64
from pathlib import PurePath, Path

from ..core.rule import IRule

class IFile(ABC):
    @property
    @abstractmethod
    def path(self) -> Path: ...


class IVFile(IFile):
    @abstractmethod
    def get_hash(self) -> str: ...


class File(IFile):
    def __init__(self, path: Union[str, os.PathLike]):
        assert isinstance(path, (str, os.PathLike))
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def __hash__(self):
        return hash(self._path)

    def __eq__(self, other):
        return type(other) == type(self) and self._path == other._path

    def __repr__(self):
        return f'{type(self).__name__}(path={repr(self.path)})'


class VFile(IVFile, File):
    def _clean(self) -> None:
        try:
            os.remove(self._path)
            os.remove(self.metadata_fname)
        except:
            pass

    def get_hash(self) -> str:
        return get_hash(self.path)
        

_hash_cache: dict[str, tuple[float, str]] = {}

def get_hash(fname: Union[str, PurePath]) -> str:
    fname = os.path.realpath(fname)

    if fname in _hash_cache:
        if os.path.getmtime(fname) == _hash_cache[fname][0]:
            return _hash_cache[fname][1]

    mtime = os.path.getmtime(fname)

    with open(fname, 'rb') as f:
        res = base64.b64encode(hashlib.md5(f.read()).digest()).decode()

    _hash_cache[fname] = (mtime, res)

    return res
