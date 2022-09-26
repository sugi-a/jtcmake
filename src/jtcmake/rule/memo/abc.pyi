import os
from abc import ABCMeta, abstractmethod
from typing import Any

class IMemo(metaclass=ABCMeta):
    @abstractmethod
    def compare(self, other_memo: Any) -> bool: ...

    @property
    @abstractmethod
    def memo(self) -> Any: ...

    def save_memo(self, fname: str|os.PathLike) -> None: ...

    def compare_to_saved(self, fname: str|os.PathLike) -> bool: ...


class IMemoAtom(metaclass=ABCMeta):
    @property
    @abstractmethod
    def memo_value(self) -> Any: ...


class ILazyMemoValue(metaclass=ABCMeta):
    @abstractmethod
    def __call__(self) -> Any: ...
    
