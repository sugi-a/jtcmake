from __future__ import annotations
import os
from pathlib import Path
from typing import Union

import pytest

from jtcmake import (
    SELF,
    GroupOfGroups as GGroup,
    GroupOfRules as RGroup,
    StaticGroupBase,
)
from jtcmake.group_tree.core import IGroup


class Group1(StaticGroupBase):
    ...


class Group2(StaticGroupBase):
    ...


def write(dst: Path, c: str):
    dst.write_text(c)


def test_basic(tmp_path: Path):
    ggggr: GGroup[GGroup[GGroup[RGroup]]] = GGroup(tmp_path)
    ggggr.set_default_child(GGroup)

    for i in range(2):
        gggr = ggggr.add_group(f"sub{i}").set_props(GGroup, prefix=f"{i}-")

        for j in range(2):
            ggr = gggr.add_group(f"sub{j}").set_props(RGroup, prefix=f"{j}-")

            for k in range(2):
                gr = ggr.add_group(f"sub{k}").set_prefix(prefix=f"{k}-")

                for i in range(2):
                    gr.add(f"r{i}", write)(SELF, "a")

    assert os.path.abspath(ggggr.sub0.sub0.sub0.r0[0]) == os.path.abspath(
        tmp_path / "0-0-0-r0"
    )


def test_add_group_union():
    g: GGroup[Union[Group1, Group2]] = GGroup()

    g.add_group("a", Group1)
    g.add_group("b", Group2)

    assert isinstance(g["a"], Group1)
    assert isinstance(g["b"], Group2)


def test_add_group_err_no_child():
    g: GGroup[Group1] = GGroup()

    with pytest.raises(Exception):
        g.add_group("a")


def test_add_group_err_dupe_name():
    g: GGroup[Group1] = GGroup()
    g.set_default_child(Group1)

    g.add_group("a")

    with pytest.raises(KeyError):
        g.add_group("a")


def test_err_abstract_child():
    g: GGroup[IGroup] = GGroup()

    with pytest.raises(TypeError):
        g.set_default_child(IGroup)

    g: GGroup[IGroup] = GGroup()

    with pytest.raises(TypeError):
        g.add_group("a", IGroup)
