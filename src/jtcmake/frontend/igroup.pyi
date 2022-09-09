import abc
from abc import ABC, abstractmethod
from collections.abc import Mapping as Mapping
from typing import Optional, overload, Callable, Any

class IGroup(ABC, metaclass=abc.ABCMeta):
    @abstractmethod
    def add_group(self, name, dirname, *, prefix): ...
    @abstractmethod
    @overload
    def add(
        self,
        name: str,
        method: Callable,
        *args,
        force_update: bool = False,
        **kwargs
    ) -> Any: ...
    @abstractmethod
    @overload
    def add(
        self,
        name: str,
        output_file_struct: Any,
        method: Callable,
        *args,
        force_update: bool = False,
        **kwargs
    ) -> Any: ...
    @abstractmethod
    @overload
    def add(
        self,
        name: str,
        method: None,
        *args,
        force_update: bool = False,
        **kwargs
    ) -> Callable[[Callable], Any]: ...
    @abstractmethod
    @overload
    def add(
        self,
        name: str,
        output_file_struct: Any,
        method: None,
        *args,
        force_update: bool = False,
        **kwargs
    ) -> Callable[[Callable], Any]: ...
    @abstractmethod
    def addvf(self, name: str, *args, **kwargs): ...
    @abstractmethod
    def make(
        self,
        dry_run: bool = ...,
        keep_going: bool = ...,
        *,
        nthreads: int = ...
    ): ...
    @abstractmethod
    def clean(self): ...
    @abstractmethod
    def touch(self, _t: Optional[float] = ...): ...
    @abstractmethod
    def select(self, pattern: str): ...
    @abstractmethod
    def __getitem__(self, k): ...
    @abstractmethod
    def __iter__(self): ...
    @abstractmethod
    def __len__(self): ...
    @abstractmethod
    def __contains__(self, k): ...
