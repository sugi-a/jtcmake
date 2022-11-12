from __future__ import annotations
from typing import Generic, TypeVar, Union

import pytest

from jtcmake.group_tree import groups
from jtcmake.group_tree.groups import GroupOfGroups as GGroup, UntypedGroup


T = TypeVar("T")


class A(Generic[T]):
    ...


@pytest.mark.parametrize(
    "type_hint,expect",
    [
        (int, int),
        (A, A),
        (A[int], A),
        (Union[A[int], int], None),
        (1, None),
    ],
)
def test_get_type(type_hint: object, expect: object):
    func = groups._get_type  # pyright: ignore [reportPrivateUsage]
    assert func(type_hint) == expect


@pytest.mark.parametrize(
    "child_group_type,expect",
    [
        (UntypedGroup, UntypedGroup),
        (GGroup[UntypedGroup], GGroup),
        (1, None),
        (groups.IGroup, None),
        (Union[UntypedGroup, GGroup[UntypedGroup]], None),
    ],
)
def test_parse_child_group_type(child_group_type: object, expect: object):
    f = groups._parse_child_group_type  # pyright: ignore [reportPrivateUsage]

    if expect is None:
        with pytest.raises(TypeError):
            f(child_group_type)
    else:
        assert f(child_group_type) == expect
