from __future__ import annotations
import abc
from typing import Callable, Any, Sequence

class Event:
    def __init__(self, msg:Any=None):
        self.msg = msg


class IRule(abc.ABC):
    @abc.abstractmethod
    def should_update(self, updated_rules: set[IRule], dry_run: bool): ...

    @abc.abstractmethod
    def preprocess(self, callback: Callable[[Event], None]): ...

    @abc.abstractmethod
    def postprocess(self, callback: Callable[[Event], None], succ: bool): ...

    @property
    @abc.abstractmethod
    def method(self) -> Callable: ...

    @property
    @abc.abstractmethod
    def args(self) -> tuple[Any]: ...

    @property
    @abc.abstractmethod
    def kwargs(self) -> dict[Any, Any]: ...

    @property
    @abc.abstractmethod
    def deplist(self) -> Sequence[IRule]: ...

