# type: ignore
from __future__ import annotations
import os
from pathlib import Path
from collections.abc import Container, Collection, Iterator

import pytest

from jtcmake.rule.file import IFile
from jtcmake.group_tree import rule
from jtcmake.group_tree.atom import Atom

class Path_:
    """Fake object to represent an PathLike[str] object"""
    def __init__(self, p: str) -> None:
        self.p = p

    def __fspath__(self) -> str:
        return self.p


class DummyFile(IFile):
    """Fake object to represent an IFile object"""

    def copy_with(self, path) -> IFile:
        return DummyFile(path)

    @property
    def memo_value(self):
        ...


class DummyFile2(IFile):
    """Fake object to represent an IFile object"""

    def copy_with(self, path) -> IFile:
        return DummyFile2(path)

    @property
    def memo_value(self):
        ...


class DummyCollection(Collection):
    """Fake object to represent a Collection object"""

    def __init__(self, c: Collection) -> None:
        self.c = c

    def __contains__(self, __x: object) -> bool:
        return __x in self.c

    def __iter__(self) -> Iterator[object]:
        return iter(self.c)

    def __len__(self) -> int:
        return len(self.c)


class DummyContainer(Container):
    """Fake object to represent a Container object"""

    def __init__(self, c: Container) -> None:
        self.c = c

    def __contains__(self, __x: object) -> bool:
        return __x in self.c

absp = os.path.abspath


@pytest.mark.parametrize("func,args,kwargs,ok", [
    (lambda: ..., (), {}, True),
    (lambda x, y: (x, y), (1,), {"y": 1}, True),
    (lambda x=1, y=1: (x, y), (), {"x": 1}, True),
    (lambda x, y: (x, y), (), {}, False),
    (lambda x, y: (x, y), (1, 1, 1), {}, False),
])
def test_assert_signature_match(func, args, kwargs, ok):
    if ok:
        rule._assert_signature_match(func, args, kwargs)
    else:
        with pytest.raises(TypeError):
            rule._assert_signature_match(func, args, kwargs)
            

@pytest.mark.parametrize("args,expect", [
    (Atom(1, 2), 1),
    (DummyFile("a"), Path("a")),
    ({1: [(Atom(1, 2), DummyFile("a"))]}, {1: [(1, Path("a"))]})
])
def test_replace_Atom_and_IFile(args, expect):
    assert rule._replace_Atom_and_IFile(args) == expect


@pytest.mark.parametrize("ypaths,args,expect", [
    (
        DummyContainer([absp("a"), absp("b")]),
        { 1: [(DummyFile("a"), DummyFile("x"))] },
        {absp("x"): DummyFile("x")}
    ),
    (
        DummyContainer([absp("a"), absp("b")]),
        { 1: [(DummyFile("a"), Path("x"))] },
        {}
    ),
])
def test_find_xfiles_in_args(ypaths, args, expect):
    assert rule._find_xfiles_in_args(ypaths, args) == expect


@pytest.mark.parametrize("ypaths,args,ok",[
    (
        DummyCollection({absp("a"), absp("b")}),
        [DummyFile("a"), {1: DummyFile("b")}],
        True
    ),
    (
        DummyCollection({absp("a"), absp("b")}),
        [DummyFile("a"), {1: Path("b")}],
        False
    ),
])
def test_assert_all_yfiles_used_in_args(ypaths, args, ok):
    if ok:
        rule._assert_all_yfiles_used_in_args(ypaths, args)
    else:
        with pytest.raises(ValueError):
            rule._assert_all_yfiles_used_in_args(ypaths, args)
            

@pytest.mark.parametrize("files,args,expect", [
    (
        {"x": DummyFile("a")},
        [(1, rule.SELF.x)],
        [(1, DummyFile("a"))]
    ),
    (
        {"x": DummyFile("a")},
        [(1, rule.SELF["x"])],
        [(1, DummyFile("a"))]
    ),
    (
        {"x": DummyFile("a")},
        [(1, rule.SELF)],
        [(1, DummyFile("a"))]
    ),
    (
        {"x": DummyFile("a"), "y": DummyFile("b")},
        [(1, rule.SELF[1])],
        [(1, DummyFile("b"))],
    ),
    (
        {"x": DummyFile("a"), "y": DummyFile("b")},
        [(1, rule.SELF)],
        Exception(),
    ),
])
def test_replace_self(files, args, expect):
    if isinstance(expect, Exception):
        with pytest.raises(type(expect)):
            rule._replace_self(files, args)
    else:
        assert rule._replace_self(files, args) == expect


def test_replace_obj_by_atom_in_structure():
    objs = [0, {}]
    atoms = [Atom(o, None) for o in objs]
    store = { id(o): a for o, a in zip(objs, atoms)}
    args = [{"a": (*objs, 1)}]
    expect = [{"a": (*atoms, 1)}]
    assert rule._replace_obj_by_atom_in_structure(store, args) == expect


@pytest.mark.parametrize("ofiles,expect",[
    (
        {"a": "a", "b": Path_("b"), "c": DummyFile2("c")},
        {"a": DummyFile("a"), "b": DummyFile("b"), "c": DummyFile2("c")},
    ),
    (
        ["a", Path_("b"), DummyFile2("c")],
        {"a": DummyFile("a"), "b": DummyFile("b"), "c": DummyFile2("c")},
    ),
    (
        "a",
        {"a": DummyFile("a")},
    ),
    (
        {"a": "{F}{R}", "b": Path_("{F}{R}")},
        {"a": DummyFile("ar"), "b": DummyFile("br")},
    ),
    (
        ["a{R}", Path_("b{R}")],
        {"ar": DummyFile("ar"), "br": DummyFile("br")},
    ),
    (
        ["{F}"],
        ValueError(),
    ),
    (
        "{F}",
        ValueError(),
    ),
])
def test_parse_args_output_files(ofiles, expect):
    if isinstance(expect, Exception):
        with pytest.raises(type(expect)):
            rule.parse_args_output_files("r", None, ofiles, DummyFile)

        return

    keys = list(expect.keys())

    assert rule.parse_args_output_files("r", None, ofiles, DummyFile) == expect
    assert rule.parse_args_output_files("r", keys, ofiles, DummyFile) == expect

    with pytest.raises(Exception):
        rule.parse_args_output_files(["x"], ofiles, DummyFile)

    with pytest.raises(Exception):
        rule.parse_args_output_files([*keys, "x"], ofiles, DummyFile)


@pytest.mark.parametrize("method,expect", [
    (lambda: None, ((), {})),
    (lambda x=1: x, ((), {"x": 1})),
    (lambda x: x, TypeError()),
    (None, TypeError()),
])
def test_Rule_init_parse_deco_func(method, expect):
    if isinstance(expect, Exception):
        with pytest.raises(type(expect)):
            rule.Rule_init_parse_deco_func(method) == expect
    else:
        rule.Rule_init_parse_deco_func(method) == expect


