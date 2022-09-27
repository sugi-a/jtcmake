from abc import abstractmethod, ABCMeta
import os
from os import PathLike
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
    ParamSpec,
    Generic,
    List,
    Dict,
    Mapping,
    Set,
)
from typing_extensions import Protocol
from logging import Logger

from ..core.abc import IRule
from ..rule.file import IFile, File, VFile
from ..utils.frozen_dict import FrozenDict
from ..core.make import MakeSummary

T = TypeVar("T")
P = ParamSpec("P")


class _ItemSet(Mapping[str, T]):
    def __getattr__(self, k: str) -> T: ...
    def __getitem__(self, k: str) -> T: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...


class Rule(FrozenDict[str, IFile]):
    def make(
        self,
        dry_run: bool = False,
        keep_going: bool = False,
        *,
        njobs: None | int = None,
    ) -> MakeSummary: ...

    def touch_memo(self) -> None: ...

    def touch(self, create=False, _t=None) -> None: ...

    def clean(self) -> None: ...


TOutput: TypeAlias = \
    str|PathLike|Sequence[str|PathLike]|Mapping[str, str|PathLike]

class Group:
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
        self,
        name: str,
        output: TOutput,
        method: Callable[P, Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Rule: ...

    @overload
    def add(
        self,
        name: str,
        output: TOutput,
        method: None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]: ...

    @overload
    def add(
        self,
        output: TOutput,
        method: Callable[P, Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Rule: ...

    @overload
    def add(
        self,
        output: TOutput,
        method: None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]: ...

    @overload
    def addvf(
        self,
        name: str,
        output: TOutput,
        method: Callable[P, Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Rule: ...

    @overload
    def addvf(
        self,
        name: str,
        output: TOutput,
        method: None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]: ...

    @overload
    def addvf(
        self,
        output: TOutput,
        method: Callable[P, Any],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Rule: ...

    @overload
    def addvf(
        self,
        output: TOutput,
        method: None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]: ...

    @overload
    def add2(
        self,
        name: str,
        output: TOutput,
        method: Callable[P, Any],
    ) -> Callable[P, Any]: ...

    @overload
    def add2(
        self,
        output: TOutput,
        method: Callable[P, Any],
    ) -> Callable[P, Any]: ...

    def clean(self) -> None: ...
    def touch(self, create: bool = False, _t: None | float = None): ...

    def select_groups(self, pattern: str|Sequence[str]) -> List[Group]: ...
    def select_rules(self, pattern: str|Sequence[str]) -> List[Rule]: ...
    def select_files(self, pattern: str|Sequence[str]) -> List[IFile]: ...

    @property
    def G(self) -> _ItemSet[Group]: ...
    @property
    def R(self) -> _ItemSet[Rule]: ...
    @property
    def F(self) -> _ItemSet[IFile]: ...

    def mem(self, value: T, memoized_value: Any) -> T: ...
    def memstr(self, value: T) -> T: ...
    def memnone(self, value: T) -> T: ...

    def __getitem__(self, k: str) -> Group: ...
    def __getattr__(self, k: str) -> Group: ...
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
) -> Group: ...

def make(
    *rule_or_groups: Sequence[Rule | Group],
    dry_run: bool = False,
    keep_going: bool = False,
    njobs: None | int = None,
) -> MakeSummary: ...

SELF: Any
