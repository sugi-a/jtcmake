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

class IFileNode(ABC):
    @property
    @abstractmethod
    def path(self) -> Any: ...
    @abstractmethod
    def touch(self, create: bool = False, _t: None | float = None): ...
    @abstractmethod
    def clean(self): ...

class IGroup(ABC): ...
