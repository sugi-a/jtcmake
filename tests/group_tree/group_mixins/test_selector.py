import pytest

from jtcmake.group_tree.core import IGroup
from jtcmake.group_tree.groups import GroupOfGroups, GroupOfRules, UntypedGroup
from jtcmake.group_tree.group_mixins import selector


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
    g2 = g1.add_group("g2", UntypedGroup)
    g3 = g1.add_group("g3", UntypedGroup)
    g4 = g3.add_group("g4", UntypedGroup)  # pyright: ignore

    assert selector.get_offspring_groups(g1) == [g1, g2, g3, g4]
