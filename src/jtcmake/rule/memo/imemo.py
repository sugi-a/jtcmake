from abc import ABC, abstractmethod


class IMemo(ABC):
    @abstractmethod
    def compare(self, args):
        ...

    @property
    @abstractmethod
    def memo(self):
        ...
