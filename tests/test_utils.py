import pytest

from jtcmake.utils.nest import map_structure, flatten, nest_get


def add1(x):
    return x + 1

@pytest.mark.parametrize(
    "x,x2",
    [
        (1, 2),
        ((1, 1), (2, 2)),
        ({"a": 1, (1, 2): [1, 1, 1]}, {"a": 2, (1, 2): [2, 2, 2]}),
        ([], []),
    ],
)
def test_map_structure(x, x2):
    assert map_structure(lambda x: x, x) == x
    assert map_structure(lambda x: 2 * x, x) == x2


@pytest.mark.parametrize(
    "x,keys,y",
    [
        (1, (), 1),
        ([1], (0,), 1),
        ([[1]], (0,), [1]),
        ({"a": {"b": [1]}}, ("a", "b", 0), 1),
    ],
)
def test_nest_get(x, keys, y):
    assert nest_get(x, keys) == y
