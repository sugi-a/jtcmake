from abc import ABC, abstractmethod, ABCMeta
import os
from pathlib import Path
from typing import Union

from .memo.abc import IMemoAtom

_hash_cache: dict[str, str]

class IFile(Path, IMemoAtom):
    @abstractmethod
    def replace(self, path: str|os.PathLike) -> IFile: ...

    
class File(IFile):
    def __init__(self, path: str|os.PathLike): ...

    @property
    def memo_value(self) -> None: ...

    def replace(self, path: str|os.PathLike) -> File: ...


class VFile(IFile):
    def __init__(self, path: str|os.PathLike): ...

    @property
    def memo_value(self) -> str: ...

    def replace(self, path: str|os.PathLike) -> VFile: ...


def get_hash(fname: str|os.PathLike) -> str: ...
