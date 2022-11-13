from __future__ import annotations
import shutil
from pathlib import Path
from typing import Literal, Union

from jtcmake import SELF, Rule, GroupsGroup, StaticGroupBase


def write(dst: Path, c: str):
    dst.write_text(c)


def copy(src: Path, dst: Path):
    shutil.copy(src, dst)


def assert_content(path: Path, content: Union[None, str]):
    if content is None:
        assert not path.exists()
    else:
        assert path.read_text() == content


"""
<root>: Static1
|
|-- r1: Rule
|   |-- a: File "r1-a"
|   `-- b: File "r1-b"
|
|-- r2: Rule
|   `-- r2: File "r2"
|
`-- g1: GroupsGroup[Static2]
    |
    |-- sub1: Static2
    |   |
    |   `-- r1: Rule
    |       `-- a: File "a.txt"
    `-- sub2: Static2
        |
        `-- r1: Rule
            `-- a: File "a.txt"
"""


class Static1(StaticGroupBase):
    r1: Rule[Literal["a", "b"]]
    r2: Rule[str]

    g1: GroupsGroup[Static2]

    def init(self, text1: str, text2: str) -> Static1:
        @self.r1.init_deco({"a": "<R>-<F>", "b": "<R>-<F>"})
        def _(  # pyright: ignore [reportUnusedFunction]
            a: Path = SELF.a, b: Path = SELF.b, t1: str = text1, t2: str = text2
        ):
            a.write_text(t1)
            b.write_text(t2)

        self.r2.init("<R>", copy)(self.r1.a, SELF)

        self.g1.set_default_child(Static2)
        self.g1.add_group("sub1").init(self.r1[0])
        self.g1.add_group("sub2").init(self.r1[1])

        return self


class Static2(StaticGroupBase):
    r1: Rule[str]

    def init(self, src: Path) -> Static2:
        self.r1.init({"a": "<F>.txt"}, copy)(src, SELF)
        return self


def test_StaticGroup(tmp_path: Path):
    g = Static1(tmp_path).init("a", "b")

    assert g.parent == g
    assert g.g1.parent == g
    assert g.rules == {
        "r1": g.r1,
        "r2": g.r2,
    }
    assert g.groups == {"g1": g.g1}


def test_StaticGroup_make(tmp_path: Path):
    g = Static1(tmp_path).init("a", "b")

    g.g1.sub1.r1.make()

    assert_content(g.r1.a, "a")
    assert_content(g.r1.b, "b")
    assert_content(g.r2[0], None)
    assert_content(g.g1.sub1.r1[0], "a")
    assert_content(g.g1.sub2.r1[0], None)

    g.make()

    assert_content(g.r1.a, "a")
    assert_content(g.r1.b, "b")
    assert_content(g.r2[0], "a")
    assert_content(g.g1.sub1.r1[0], "a")
    assert_content(g.g1.sub2.r1[0], "b")
