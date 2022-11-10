from typing import Iterator, TypeVar, Mapping

K = TypeVar("K")
V = TypeVar("V")


class DictView(Mapping[K, V]):
    def __init__(self, dic: Mapping[K, V]):
        self._dic = dic

    def __getitem__(self, key: K) -> V:
        return self._dic[key]

    def __iter__(self) -> Iterator[K]:
        return self._dic.__iter__()

    def __len__(self) -> int:
        return len(self._dic)

    def __contains__(self, key: object) -> bool:
        return key in self._dic

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{dict(self)}"
