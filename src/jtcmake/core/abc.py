from __future__ import annotations
from abc import ABCMeta, abstractmethod
from collections.abc import Set
from typing import Any, Callable, Generic, Union
from typing_extensions import ParamSpec, TypeAlias


class UpToDate:
    ...


class Necessary:
    ...


class PossiblyNecessary:
    # dry_run only
    ...


class Infeasible:
    def __init__(self, reason):
        """
        Args:
            reason (str): reason
        """
        self.reason = reason


class UpdateResults:
    UpToDate = UpToDate
    Necessary = Necessary
    PossiblyNecessary = PossiblyNecessary
    Infeasible = Infeasible


TUpdateResult: TypeAlias = Union[
    UpToDate, Necessary, PossiblyNecessary, Infeasible
]


class IEvent:
    ...


_Callback = Callable[[IEvent], None]
P = ParamSpec("P")


class IRule(Generic[P], metaclass=ABCMeta):
    @abstractmethod
    def check_update(self, par_updated: bool, dry_run: bool) -> TUpdateResult:
        ...

    @abstractmethod
    def preprocess(self, callback: _Callback) -> None:
        ...

    @abstractmethod
    def postprocess(self, callback: _Callback, succ: bool) -> None:
        ...

    @property
    @abstractmethod
    def method(self) -> Callable[P, Any]:
        ...

    @property
    @abstractmethod
    def args(self) -> Any:
        ...

    @property
    @abstractmethod
    def kwargs(self) -> Any:
        ...

    @property
    @abstractmethod
    def deps(self) -> Set[int]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
