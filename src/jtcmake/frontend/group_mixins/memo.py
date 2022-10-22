from typing import TypeVar
from ..group_common import IGroup
from ..atom import Atom

T = TypeVar("T")

class MemoMixin(IGroup):
    def mem(self, value: T, memoized_value: object) -> T:
        self._get_info().memo_store[id(value)] = Atom(value, memoized_value)
        return value

    def memstr(self, value: T) -> T:
        return self.mem(value, str(value))

    def memnone(self, value: T) -> T:
        return self.mem(value, None)


