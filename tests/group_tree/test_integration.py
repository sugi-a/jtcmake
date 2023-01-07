from pathlib import Path

import pytest

from jtcmake import SELF, Rule, StaticGroupBase, UntypedGroup


class Group(StaticGroupBase):
    a: Rule[str]


def test_guard_outputless_rule():
    g = Group()

    def _f():
        ...

    with pytest.raises(ValueError):
        g.a.init({}, _f)()


def test_error_on_dupe_registration():
    # rule -> group
    g = UntypedGroup()
    g.add("a", Path.write_text)(SELF, "a")
    with pytest.raises(KeyError):
        g.add_group("a")

    # group -> rule
    g = UntypedGroup()
    g.add_group("a")
    with pytest.raises(KeyError):
        g.add("a", Path.write_text)(SELF, "a")


def test_noskip(tmp_path: Path):
    g = UntypedGroup(tmp_path)

    flag = False

    @g.add("a", noskip=True)
    def _(slf: Path = SELF):
        nonlocal flag
        flag = True
        slf.touch()

    g.make()
    assert flag
    flag = False
    g.make()
    assert flag


def test_file_dir_collision():
    def fn(_: Path):
        ...

    g = UntypedGroup()
    g.add("a", fn)(SELF)

    with pytest.raises(Exception):
        g.add("a/b.txt", fn)(SELF)

    g = UntypedGroup()
    g.add("a/b.txt", fn)(SELF)

    with pytest.raises(Exception):
        g.add("a", fn)(SELF)

    g = UntypedGroup()
    g.add("a", fn)(SELF)
