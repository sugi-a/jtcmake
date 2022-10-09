from collections.abc import Mapping
from typing import TypeVar, Any

K = TypeVar("K")
V = TypeVar("V")


class FrozenDict(Mapping[K, V]):
    def __init__(self, dic: Mapping[K, V]):
        self._dic = dic

    def __getitem__(self, key: K) -> V:
        return self._dic[key]

    def __iter__(self):
        return self._dic.__iter__()

    def __len__(self):
        return len(self._dic)

    def __contains__(self, key):
        return key in self._dic

    def __repr__(self):
        return f"FrozenDict{dict(self)}"

    def __getattr__(self, key: Any) -> V:
        return self._dic[key]
