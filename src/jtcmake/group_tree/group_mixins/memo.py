from typing import TypeVar

from ..atom import Atom
from ..core import INode

T = TypeVar("T")


class MemoMixin(INode):
    def mem(self: INode, value: T, memoized_value: object) -> T:
        self._get_info().memo_store[id(value)] = Atom(value, memoized_value)
        return value

    def memstr(self: INode, value: T) -> T:
        return MemoMixin.mem(self, value, str(value))

    def memnone(self: INode, value: T) -> T:
        return MemoMixin.mem(self, value, None)
