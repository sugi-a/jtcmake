from __future__ import annotations
import json
from abc import ABCMeta, abstractmethod

from typing import Type, Tuple, List, Union

from ..utils.nest import ordered_map_structure

from ..utils.strpath import StrOrPath
from ..raw_rule import IMemo


class IMemoWrapper(IMemo, metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def create(cls, args: object) -> IMemoWrapper:
        ...

    @abstractmethod
    def to_str(self) -> str:
        ...

    @classmethod
    @abstractmethod
    def from_str(cls, s: str) -> IMemoWrapper:
        ...

    @classmethod
    def load(cls, path: StrOrPath) -> IMemoWrapper:
        with open(path, "r") as f:
            return cls.from_str(f.read())

    def save(self, path: StrOrPath):
        with open(path, "w") as f:
            f.write(self.to_str())


class ILazyMemo(IMemoWrapper):
    @property
    def memo(self) -> IMemoWrapper:
        ...

    @property
    def lazy_memo(self) -> IMemoWrapper:
        ...


def create_lazy_memo_type(memo_type: Type[IMemoWrapper]) -> Type[IMemoWrapper]:
    class LazyMemo(ILazyMemo):
        __slots__ = ("_memo", "lazy_args")
        _memo: IMemoWrapper
        lazy_args: Union[List[ILazyMemoValue], IMemoWrapper]

        def __init__(
            self,
            memo: IMemoWrapper,
            lazy_args: Union[List[ILazyMemoValue], IMemoWrapper],
        ):
            self._memo = memo
            self.lazy_args = lazy_args

        @property
        def memo(self) -> IMemoWrapper:
            return self._memo

        @property
        def lazy_memo(self) -> IMemoWrapper:
            if isinstance(self.lazy_args, list):
                lazy_args = [v() for v in self.lazy_args]
                return self.memo.create(lazy_args)
            else:
                return self.lazy_args

        def compare(self, other: IMemo) -> bool:
            if isinstance(other, ILazyMemo):
                return self.memo.compare(other.memo) and self.lazy_memo.compare(
                    other.lazy_memo
                )
            else:
                return False

        @classmethod
        def create(cls, args: object) -> ILazyMemo:
            args, lazy_args = unwrap_atoms_in_nest(args)
            return cls(memo_type.create(args), lazy_args)

        @classmethod
        def from_str(cls, s: str) -> ILazyMemo:
            o = json.loads(s)
            assert isinstance(o, list)

            memo = memo_type.from_str(o[0])
            lazy_args = memo_type.from_str(o[1])

            return cls(memo, lazy_args)

        def to_str(self) -> str:
            return json.dumps([self.memo.to_str(), self.lazy_memo.to_str()])

    return LazyMemo


class IMemoAtom(metaclass=ABCMeta):
    @property
    @abstractmethod
    def memo_value(self) -> object:
        """
        Returns:
            object to be memoized
        """
        ...


class ILazyMemoValue(metaclass=ABCMeta):
    @abstractmethod
    def __call__(self) -> object:
        """
        Returns:
            object to be memoized.
        """
        ...


def unwrap_atoms_in_nest(nest: object) -> Tuple[object, List[ILazyMemoValue]]:
    lazy_values: List[ILazyMemoValue] = []

    def _unwrap_atom(atom: object):
        if isinstance(atom, IMemoAtom):
            v = atom.memo_value
            if isinstance(v, ILazyMemoValue):
                lazy_values.append(v)
                return None
            else:
                return v
        else:
            return atom

    nest = ordered_map_structure(_unwrap_atom, nest)

    return nest, lazy_values
