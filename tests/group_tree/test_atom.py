import pytest

from jtcmake.group_tree.atom import (
    IAtom,
    ILazyMemoValue,
    unwrap_memo_values,
    unwrap_real_values,
)


class A1(IAtom):
    @property
    def real_value(self) -> object:
        return 1

    @property
    def memo_value(self) -> object:
        return 2


class A2(IAtom):
    @property
    def real_value(self) -> object:
        return 1

    @property
    def memo_value(self) -> object:
        return Lazy()


class Lazy(ILazyMemoValue):
    def __call__(self) -> object:
        return 2


a1, a2 = A1(), A2()


@pytest.mark.parametrize(
    "args,expect",
    [
        (a1, 1),  # atom
        ((a1, a2), (1, 1)),  # tuple
        ([a1, a2], [1, 1]),  # list
        ({"a": a1}, {"a": 1}),  # dict
        ({a1, a2}, set([1])),  # set
        ({"a": [a1]}, {"a": [1]}),  # compound
    ],
)
def test_unwrap_real_values(args: object, expect: object):
    assert unwrap_real_values(args) == expect


@pytest.mark.parametrize(
    "args,expect_v,expect_l",
    [
        (a1, 2, []),  # atom
        ((a1, a2), (2, None), [2]),  # tuple
        ([a1, a2], [2, None], [2]),  # list
        ({"a": a1, "b": a2}, {"a": 2, "b": None}, [2]),  # dict
        ({a1, a2}, {2, None}, [2]),  # set
        ({"a": [a1]}, {"a": [2]}, []),  # compound
    ],
)
def test_unwrap_memo_values(args: object, expect_v: object, expect_l: object):
    a, b = unwrap_memo_values(args)
    assert a == expect_v
    assert b() == expect_l
