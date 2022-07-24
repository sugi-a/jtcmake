from typing import Optional
from abc import ABC, abstractmethod
from collections.abc import Mapping

class IGroup(ABC):
    @abstractmethod
    def add_group(self, name, dirname, *, prefix): ...

    @abstractmethod
    def add(self, name: str, *args, **kwargs): ...

    @abstractmethod
    def addvf(self, name, *args, **kwargs): ...

    @abstractmethod
    def make(self, dry_run=False, keep_going=False, *, nthreads=1): ...

    @abstractmethod
    def clean(self): ...

    @abstractmethod
    def touch(self, _t: Optional[float]=None): ...
    
    @abstractmethod
    def select(self, pattern: str): ...

    @abstractmethod
    def print_graphviz(self, output_file=None): ...

    @abstractmethod
    def __getitem__(self, k): ...

    @abstractmethod
    def __iter__(self): ...

    @abstractmethod
    def __len__(self): ...

    @abstractmethod
    def __contains__(self, k): ...

