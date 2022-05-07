import sys, os, time
import pytest

from lightmake.utils import map_nested, flatten_nested, get_deep, should_update

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
def test_map_nested(fn, x, y):
    assert map_nested(x, fn) == y


@pytest.mark.parametrize(
    "x,y", [
        (1, [1]),
        ([1,1], [1,1]),
        ({'a': 1, 0: (2,3)}, [1,2,3]),
    ]
)
def test_flatten_nested(x, y):
    y_ = flatten_nested(x)
    y_.sort()
    assert y_ == y


@pytest.mark.parametrize(
    "x,keys,y", [
        (1, (), 1),
        ([1], (0,), 1),
        ([[1]], (0,), [1]),
        ({'a': {'b': [1]}}, ('a', 'b', 0), 1),
    ]
)
def test_get_deep(x, keys, y):
    assert get_deep(x, keys) == y
    

def test_should_update(tmp_path):
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    c = tmp_path / 'c'
    d = tmp_path / 'd'
    x = tmp_path / 'x'

    for p in (a,b,c,d):
        p.touch()

    t = time.time()
    for p,d in [(a,1), (b,2), (c,3), (d,4)]:
        os.utime(p, (t - 1000, t - 1000 * d))

    assert not should_update([a,b], [c,d])
    assert not should_update([a], [b])
    assert should_update([c,d], [a,b])
    assert should_update([a,c], [b,d])
    assert not should_update([], [a])
    assert not should_update([a], [])
    assert not should_update([a], [])
    assert should_update([x], [a])
    assert should_update([x], [])

    with pytest.raises(FileNotFoundError) as e:
        should_update([a], [x])



