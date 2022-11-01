# type: ignore

import os
from pathlib import Path

import pytest

from jtcmake.group_tree.core import (
    GroupTreeInfo,
    IGroup,
    INode,
    IRule,
    ItemMap,
    get_group_info_of_nodes,
    parse_args_prefix,
    concat_prefix,
    priv_add_to_itemmap,
    gather_raw_rule_ids
)


@pytest.mark.parametrize("dirname,prefix,expect", [
    (None, "a", "a"),
    (None, Path("a"), "a"),
    ("a", None, "a" + os.path.sep),
    (Path("a"), None, "a" + os.path.sep),
    ("a", "a", TypeError),
])
def test_parse_args_prefix(dirname, prefix, expect):
    if isinstance(expect, str):
        assert parse_args_prefix(dirname, prefix) == expect
    else:
        with pytest.raises(expect):
            parse_args_prefix(dirname, prefix)


@pytest.mark.parametrize("base,prefix,expect", [
    ("a", "b", "ba"),
    (os.path.abspath("a"), "b", os.path.abspath("a")),
    ("~/a", "b", os.path.expanduser("~/a")),
])
def test_concat_prefix(base, prefix, expect):
    concat_prefix(base, prefix) == expect


def test_ItemMap():
    m = ItemMap()

    assert list(m.items()) == []
    
    priv_add_to_itemmap(m, "a", 1)

    assert list(m.items()) == [("a", 1)]


def test_gather_raw_rule_ids(mocker):
    r1 = mocker.MagicMock(IRule, raw_rule_id=1)
    g1 = mocker.MagicMock(IGroup, rules={"r1": r1})

    assert gather_raw_rule_ids([r1]) == [1]
    assert gather_raw_rule_ids([g1]) == [1]
    assert gather_raw_rule_ids([g1, g1, r1, r1]) == [1]


def test_get_group_info_of_nodes(mocker):
    n1 = mocker.MagicMock(INode)
    n2 = mocker.MagicMock(INode)

    info1 = mocker.MagicMock(GroupTreeInfo)
    info2 = mocker.MagicMock(GroupTreeInfo)

    # same tree
    n1._get_info.return_value = info1
    n2._get_info.return_value = info1

    assert get_group_info_of_nodes([n1, n2]) == info1

    # different trees
    n1._get_info.return_value = info1
    n2._get_info.return_value = info2

    with pytest.raises(ValueError):
        get_group_info_of_nodes([n1, n2])