from abc import ABC, abstractmethod


class IMemo(ABC):
    @abstractmethod
    def compare(self, args):
        ...

    @property
    @abstractmethod
    def memo(self):
        ...


class IMemoAtom(ABC):
    @property
    @abstractmethod
    def memo_value(self):
        """
        Returns:
            object to be memoized
        """
        ...


class ILazyMemoValue(ABC):
    @abstractmethod
    def __call__(self):
        """
        Returns:
            object to be memoized.
        """
        ...
