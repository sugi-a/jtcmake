from collections.abc import Mapping


class FrozenDict(Mapping):
    def __init__(self, dic):
        self._dic = dic

    def __getitem__(self, key):
        return self._dic[key]

    def __iter__(self):
        return self._dic.__iter__()

    def __len__(self):
        return len(self._dic)

    def __contains__(self, key):
        return key in self._dic

    def __repr__(self):
        return f"FrozenDict{dict(self)}"

    def __getattr__(self, key):
        return self._dic[key]
