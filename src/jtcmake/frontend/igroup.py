from abc import ABC, abstractmethod
from collections.abc import Mapping

class IGroup(ABC):
    @abstractmethod
    def add_group(self, name, dirname, *, prefix): ...

    @abstractmethod
    def add(self, name, *args, **kwargs): ...

    @abstractmethod
    def addvf(self, name, *args, **kwargs): ...

    @abstractmethod
    def make(self, dry_run=False, keep_going=False, *, nthreads=1): ...

    @abstractmethod
    def clean(self): ...

    @abstractmethod
    def touch(self, _t=None): ...
    
    @abstractmethod
    def select(self, pattern): ...

    @abstractmethod
    def __getitem__(self, k): ...

    @abstractmethod
    def __iter__(self): ...

    @abstractmethod
    def __len__(self): ...

    @abstractmethod
    def __contains__(self, k): ...

