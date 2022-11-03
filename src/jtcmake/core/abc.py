from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import Any, Callable, Union, Set
from typing_extensions import TypeAlias


class UpToDate:
    ...


class Necessary:
    ...


class PossiblyNecessary:
    # dry_run only
    ...


class Infeasible:
    def __init__(self, reason: str):
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


Callback = Callable[[IEvent], None]


class IRule(metaclass=ABCMeta):
    @abstractmethod
    def check_update(self, par_updated: bool, dry_run: bool) -> TUpdateResult:
        ...

    @abstractmethod
    def preprocess(self, callback: Callback) -> None:
        ...

    @abstractmethod
    def postprocess(self, callback: Callback, succ: bool) -> None:
        ...

    @property
    @abstractmethod
    def method(self) -> Callable[..., object]:
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
