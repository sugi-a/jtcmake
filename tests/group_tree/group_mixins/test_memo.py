from jtcmake.group_tree.group_mixins.memo import MemoMixin
from jtcmake.group_tree.groups import StaticGroupBase


def test_MemoMixin():
    a, b, c, d = [object() for _ in range(4)]

    g = StaticGroupBase()

    MemoMixin.mem(g, a, b)
    MemoMixin.memstr(g, c)
    MemoMixin.memnone(g, d)

    store = g._get_info().memo_store  # pyright: ignore [reportPrivateUsage]

    assert store[id(a)].real_value == a
    assert store[id(a)].memo_value == b
    assert store[id(c)].real_value == c
    assert store[id(c)].memo_value == str(c)
    assert store[id(d)].real_value == d
    assert store[id(d)].memo_value == None
