# type: ignore

import pytest

from jtcmake.group_tree.core import IGroup
from jtcmake.group_tree.groups import UntypedGroup
from jtcmake.group_tree.group_mixins import selector
from jtcmake.group_tree.rule import SELF


@pytest.mark.parametrize("pattern,expect", [
    (["a", "b/"], ["a", "b/"]),
    ("a/b", ["a", "b"]),
    ("a/b/", ["a", "b"]),
    ("", ValueError()),
    (1, TypeError()),
])
def test_parse_args_pattern(pattern: object, expect: object):
    func = selector._parse_args_pattern  # pyright: ignore [reportPrivateUsage]
    if isinstance(expect, Exception):
        with pytest.raises(type(expect)):
            func(pattern)
    else:
        assert func(pattern) == expect


def test_get_offspring_groups():
    """
    g1
    |-- g2
    `-- g3
        `-- g4
    """
    g1 = UntypedGroup()
    g2 = g1.add_group("g2")
    g3 = g1.add_group("g3")
    g4 = g3.add_group("g4")

    assert selector.get_offspring_groups(g1) == [g1, g2, g3, g4]


def _create_group_for_test_select():
    """
    a/
    |-- a (a)
    |-- b (b1.txt, b2.txt)
    |-- c/
    |-- |-- d/
    |   `-- a (a)
    |-- d/
    `-- a/b/
        `-- a (a.txt)
    """
    def _fn(*args: object, **kwargs: object):
        ...

    g = UntypedGroup()

    g.add("a", _fn)(SELF)
    g.add("b", ["b1.txt", "b2.txt"], _fn)(SELF[0], SELF[1])

    g.add_group("c")
    g.c.add("a", _fn)(SELF)
    g.c.add_group("d")

    g.add_group("d")

    g.add_group("a/b")
    g["a/b"].add("a", "a.txt", _fn)(SELF)

    return g


def test_group_select_groups():
    g = _create_group_for_test_select()

    # no *
    assert g.select_groups("c") == [g.c]
    assert g.select_groups("c/d") == [g.c.d]

    # *
    assert g.select_groups("*") == [g.c, g.d, g["a/b"]]
    assert g.select_groups("c/*") == [g.c.d]
    assert g.select_groups("*/d") == [g.c.d]
    assert g.select_groups("*/*") == [g.c.d]

    # **
    assert g.select_groups("**") == [g, g.c, g.c.d, g.d, g["a/b"]]
    assert g.select_groups("**/d") == [g.c.d, g.d]


def test_group_select_rules():
    g = _create_group_for_test_select()

    # no *
    assert g.select_rules("a") == [g.a]

    # *
    assert g.select_rules("*") == [g.a, g.b]

    # **
    assert g.select_rules("**/a") == [g.a, g.c.a, g["a/b"].a]


def test_group_select_files():
    g = _create_group_for_test_select()

    # no *
    assert g.select_files("a/a") == [g.a.a]

    # *, **
    assert g.select_files("**/*.txt") == [g.b[0], g.b[1], g["a/b"].a[0]]
