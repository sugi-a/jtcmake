import pytest

from jtcmake.utils.nest import map_structure, flatten, struct_get

def add1(x):
    return x + 1


@pytest.mark.parametrize(
    "fn,x,y", [
        (add1, 1, 2),
        (add1, (1,2), (2,3)),
        (add1, {'a': 1, (1,2): [1,2,3]}, {'a': 2, (1,2): [2,3,4]}),
        (add1, [], []),
        (len, 'a', 1),
        (len, ['a'], [1]),
        (len, {'a': {1,2}}, {'a': 2}),
        (len, {'a': ((), ())}, {'a': ((), ())}),
    ])
def test_map_structure(fn, x, y):
    assert map_structure(fn, x) == y


@pytest.mark.parametrize(
    "x,y", [
        (1, [1]),
        ([1,1], [1,1]),
        ({'a': 1, 0: (2,3)}, None),
        ({'b': 1, 'a': (2,3)}, [2, 3, 1]),
    ]
)
def test_flatten(x, y):
    """dict keys must be sortable"""
    if y is None:
        with pytest.raises(Exception):
            flatten(x)
    else:
        assert flatten(x) == y


@pytest.mark.parametrize(
    "x,keys,y", [
        (1, (), 1),
        ([1], (0,), 1),
        ([[1]], (0,), [1]),
        ({'a': {'b': [1]}}, ('a', 'b', 0), 1),
    ]
)
def test_struct_get(x, keys, y):
    assert struct_get(x, keys) == y
