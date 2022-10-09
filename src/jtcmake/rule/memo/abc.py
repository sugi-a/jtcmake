from __future__ import annotations
import json
import os
from abc import ABCMeta, abstractmethod
from typing import Any, Union


class IMemo(metaclass=ABCMeta):
    @property
    @abstractmethod
    def memo(self) -> IMemoInstance:
        ...


class IMemoInstance(metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def get_type(cls) -> str:
        ...

    @abstractmethod
    def to_obj(self) -> Any:
        ...

    @classmethod
    @abstractmethod
    def from_obj(cls, obj: Any) -> IMemoInstance:
        ...

    @classmethod
    def load(cls, fname: Union[str, os.PathLike]) -> IMemoInstance:
        with open(fname) as f:
            data = json.load(f)
            t = data["type"]
            if t != cls.get_type():
                raise ValueError(
                    f"Invalid memo type {t}. Expected {cls.get_type()}"
                )
            return cls.from_obj(data["data"])

    def save(self, fname: Union[str, os.PathLike]):
        with open(fname, "w") as f:
            data = {"type": self.get_type(), "data": self.to_obj()}
            json.dump(data, f)

    @abstractmethod
    def compare(self, other: IMemoInstance) -> bool:
        ...


class IMemoAtom(metaclass=ABCMeta):
    @property
    @abstractmethod
    def memo_value(self):
        """
        Returns:
            object to be memoized
        """
        ...


class ILazyMemoValue(metaclass=ABCMeta):
    @abstractmethod
    def __call__(self):
        """
        Returns:
            object to be memoized.
        """
        ...
