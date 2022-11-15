from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import Callable, Union, Set, TypeVar, Generic
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


UpdateResult: TypeAlias = Union[
    UpToDate, Necessary, PossiblyNecessary, Infeasible
]


_T_Rule = TypeVar("_T_Rule", bound="IRule", covariant=True)


class IEvent(Generic[_T_Rule]):
    ...


class IRule(metaclass=ABCMeta):
    @abstractmethod
    def check_update(self, par_updated: bool, dry_run: bool) -> UpdateResult:
        ...

    @abstractmethod
    def preprocess(self) -> None:
        ...

    @abstractmethod
    def postprocess(self, succ: bool) -> None:
        ...

    @property
    @abstractmethod
    def method(self) -> Callable[[], object]:
        ...

    @property
    @abstractmethod
    def deps(self) -> Set[int]:
        ...
