from abc import abstractmethod, ABC
import os
from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path
from typing import (
    Any,
    Optional,
    Sequence,
    Union,
    overload,
    Callable,
    TypeVar,
    Iterator,
    TypeAlias,
)
from typing_extensions import Protocol
from logging import Logger

from ..core.abc import IRule
from ..rule.file import File, IFile, IVFile, VFile
from ..utils.nest import NestKey
from ..utils.frozen_dict import FrozenDict
from .abc import IGroup
from ..core.make import MakeSummary

class RuleNodeBase(ABC):
    def make(
        self,
        dry_run: bool = False,
        keep_going: bool = False,
        *,
        njobs: None | int = None,
    ) -> MakeSummary: ...
    @property
    def name(self) -> Sequence[str]: ...
    def touch_memo(self): ...
    @abstractmethod
    def clean(self): ...
    @abstractmethod
    def touch(self, create: bool = False, _t: float = None): ...

class RuleNodeAtom(RuleNodeBase):
    def clean(self): ...
    def touch(self, create: bool = False, _t: float = None): ...

class RuleNodeTuple(tuple, RuleNodeBase):
    def clean(self): ...
    def touch(self, create: bool = False, _t: float = None): ...

class RuleNodeDict(FrozenDict, RuleNodeBase):
    def clean(self): ...
    def touch(self, create: bool = False, _t: float = None): ...

_RuleNode: TypeAlias = RuleNodeAtom | RuleNodeTuple | RuleNodeDict

class Group(IGroup):
    def add_group(
        self,
        name: str | os.PathLike,
        dirname: None | str | os.PathLike = None,
        *,
        prefix: None | str | os.PathLike = None,
    ) -> Group: ...
    def make(
        self,
        dry_run: bool = False,
        keep_going: bool = False,
        *,
        njobs: None | int = None,
    ) -> MakeSummary: ...
    @overload
    def add(
        self, name: str, method: Callable, *args, **kwargs
    ) -> _RuleNode: ...
    @overload
    def add(
        self,
        name: str,
        output_file_struct: Any,
        method: Callable,
        *args,
        **kwargs,
    ) -> _RuleNode: ...
    @overload
    def add(
        self, name: str, method: None, *args, **kwargs
    ) -> Callable[[Callable], _RuleNode]: ...
    @overload
    def add(
        self, name: str, output_file_struct: Any, method: None, *args, **kwargs
    ) -> Callable[[Callable], _RuleNode]: ...
    @overload
    def addvf(
        self, name: str, method: Callable, *args, **kwargs
    ) -> _RuleNode: ...
    @overload
    def addvf(
        self,
        name: str,
        output_file_struct: Any,
        method: Callable,
        *args,
        **kwargs,
    ) -> _RuleNode: ...
    @overload
    def addvf(
        self, name: str, method: None, *args, **kwargs
    ) -> Callable[[Callable], _RuleNode]: ...
    @overload
    def addvf(
        self, name: str, output_file_struct: Any, method: None, *args, **kwargs
    ) -> Callable[[Callable], _RuleNode]: ...
    def clean(self) -> None: ...
    def touch(self, create: bool = False, _t: None | float = None): ...
    @overload
    def select(self, pattern: str, group: bool = False) -> list[_RuleNode]: ...
    @overload
    def select(
        self, pattern: list[str], group: bool = False
    ) -> list[_RuleNode]: ...
    def __getitem__(self, k: str) -> Group | _RuleNode: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __contains__(self, k: str) -> bool: ...

class Writable(Protocol):
    def write(self, text: str): ...

def create_group(
    dirname: None | str | os.PathLike = None,
    prefix: None | str | os.PathLike = None,
    *,
    loglevel: Optional[str] = None,
    use_default_logger: bool = True,
    logfile: None
    | str
    | os.PathLike
    | Logger
    | Writable
    | Sequence[str | os.PathLike | Logger | Writable] = None,
) -> IGroup: ...

SELF: NestKey

def make(
    *rule_or_groups: Sequence[_RuleNode | Group],
    dry_run: bool = False,
    keep_going: bool = False,
    njobs: None | int = None,
) -> MakeSummary: ...
