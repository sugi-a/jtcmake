import sys, os, shutil, glob, time
from pathlib import Path, PurePath

import pytest

from jtcmake.frontend.group import create_group, SELF
from jtcmake.rule.file import File, VFile
from jtcmake.utils.nest import map_structure
import jtcmake


class _PathLike:
    def __init__(self, p):
        self.p = str(p)

    def __fspath__(self):
        return self.p


fn = lambda *x, **y: None


def test_create_group():
    # no args
    with pytest.raises(TypeError):
        g = create_group()

    # memo_kind neither "str_hash" or "pickle"
    with pytest.raises(ValueError):
        g = create_group("root", memo_kind="aa")

    # memo_kind="str_hash" and non-null pickle_key
    with pytest.raises(TypeError):
        g = create_group("root", memo_kind="str_hash", pickle_key="AA")

    # memo_kind="pickle" and pickle_key=None
    with pytest.raises(TypeError):
        g = create_group("root", memo_kind="pickle")

    # memo_kind="pickle" and pickle_key=<some invalid hexadecimal str>
    with pytest.raises(ValueError):
        g = create_group("root", memo_kind="pickle", pickle_key="A")


def test_group_add_group():
    #### normal cases ####
    def _test(expect, *args, **kwargs):
        g = create_group("root").add_group(*args, **kwargs)
        assert Path(g._prefix + "_") == Path("root") / (expect + "_")

    # dirname
    _test("x/y/", "a", "x/y")
    _test("x/y/", "x/y")
    _test("x/y/", _PathLike("x/y"))
    _test(os.path.abspath("x/y/") + "/", os.path.abspath("x/y"))

    # prefix
    _test("x/y", "a", prefix="x/y")
    _test("x/y", "a", prefix="x/y")
    _test("x/y", "a", prefix=_PathLike("x/y"))
    _test(os.path.abspath("x/y"), "a", prefix=os.path.abspath("x/y"))

    # posix home dir ~
    if os.name == "posix":
        _test(os.path.expanduser("~/x/"), "~/x")
        _test(os.path.expanduser("~/x/"), "a", prefix="~/x/")

    # accessing as attribute or via dict key
    g = create_group("root")
    g.add_group("a")
    g.add_group("_a")
    g.add_group("a-")
    assert hasattr(g, "a")
    assert not hasattr(g, "_a")
    assert not hasattr(g, "a-")
    assert all((k in g) for k in ("a", "_a", "a-"))

    #### invalid calls ####
    # prefix only (name needed)
    with pytest.raises(Exception):
        create_group("root").add_group(prefix="a")

    # specify both
    with pytest.raises(Exception):
        create_group("root").add_group("a", dirname="dir", prefix="dir/")

    # specify non-(str|PathLike)
    with pytest.raises(Exception):
        create_group("root").add_group(11)

    with pytest.raises(Exception):
        create_group("root").add_group("a", 11)

    # name being empty str
    with pytest.raises(Exception):
        create_group("root").add_group("", "a")

    # overwriting registration
    g = create_group("root")
    g.add_group("a")
    with pytest.raises(Exception):
        g.add_group("a")


def test_group_add():
    APath = lambda p: Path(os.path.abspath(p))

    ######## Output file path ########
    #### atom path ####
    def _test(expect, *x):
        assert create_group("r").add(*x).abspath == APath("r") / expect
        assert create_group("r").addvf(*x).abspath == APath("r") / expect

    # str/PathLike/IFile
    _test("a1", "a", "a1", fn)
    _test("a1", "a", _PathLike("a1"), fn)
    _test("a1", "a", File("a1"), fn)
    _test("a1", "a", VFile("a1"), fn)

    # abspath
    _test(os.path.abspath("a1"), "a", os.path.abspath("a1"), fn)

    # omit path
    _test("a1", "a1", fn)

    # posix home dir
    if os.name == "posix":
        _test(os.path.expanduser("~/a1"), "a", "~/a1", fn)

    #### structured path ####
    a = create_group("r").add("a", ["a1", {"x": File("a2")}, ("a3",)], fn)
    assert a.abspath == (APath("r/a1"), {"x": APath("r/a2")}, (APath("r/a3"),))
    a = create_group("r").add("a", ["a1", "a1"], fn)
    assert a.abspath == (APath("r/a1"), APath("r/a1"))

    a = create_group("r").add(
        "d",
        [{"x": "d1.txt", "y": ["d2.txt"]}, ("d3.txt", "d4.txt")],
        lambda _: None,
    )
    assert a.abspath == (
        {"x": APath("r/d1.txt"), "y": (APath("r/d2.txt"),)},
        (APath("r/d3.txt"), APath("r/d4.txt")),
    )

    # dict key order
    a = create_group("r").add("a", {"a": "a1", "b": "a2"}, fn)
    b = create_group("r").add("a", {"b": "a2", "a": "a1"}, fn)
    assert a.abspath == b.abspath

    #### kind of IFile ####
    # add: default is File
    a = create_group("r").add("a", ["a1", VFile("a2")], fn)
    assert isinstance(a[0]._file, File)
    assert isinstance(a[1]._file, VFile)

    # addvf: default is VFile
    a = create_group("r").addvf("a", ["a1", File("a2")], fn)
    assert isinstance(a[0]._file, VFile)
    assert isinstance(a[1]._file, File)

    ######## arguments ########
    #### args and kwargs
    """
    Paths in arguments can be either relative or absolute.
    """

    def _to_abs(o):
        return map_structure(
            lambda x: Path(os.path.abspath(x)) if isinstance(x, Path) else x, o
        )

    g = create_group("r")
    g.add("a", fn, 1, a=1)
    g.add("b", fn, 1, {"a": [g.a]}, a=1, b=g.a)
    assert _to_abs(g.a._rule.args) == (g.a.abspath, 1)
    assert _to_abs(g.a._rule.kwargs) == {"a": 1}
    assert _to_abs(g.b._rule.args) == (g.b.abspath, 1, {"a": [g.a.abspath]})
    assert _to_abs(g.b._rule.kwargs) == {"a": 1, "b": g.a.abspath}

    g = create_group("r")
    g.add("a", ["a1", "a2"], fn)
    g.add("b", ["b1", "b2"], fn, g.a[0], SELF[0], SELF[1], a=SELF)
    assert _to_abs(g.b._rule.args) == (
        g.a[0].abspath,
        g.b[0].abspath,
        g.b[1].abspath,
    )
    assert _to_abs(g.b._rule.kwargs) == {"a": list(g.b.abspath)}

    g = create_group("r")
    g.add("a", fn, VFile("x"))

    assert _to_abs(g.a._rule.args) == (g.a.abspath, APath("x"))

    #### deplist
    g = create_group("r")
    g.add("a", fn)
    g.add("b", fn)
    g.add("c", fn, {"b": g.a, "a": g.b})
    assert set(g.c._rule.deplist) == set([0, 1])

    ######## invalid calls ########
    # argument type errors
    with pytest.raises(Exception):
        create_group("r").add(1, fn)

    with pytest.raises(Exception):
        create_group("r").add("a", 1, fn)

    with pytest.raises(Exception):
        create_group("r").add("a", "a", 1)

    # name being empty str
    with pytest.raises(Exception):
        create_group("root").add("", "a", fn)

    # overwriting
    g = create_group("r")
    g.add("a", fn)
    with pytest.raises(Exception):
        g.add("a", fn)

    # path collision
    g = create_group("r")
    g.add("a", "a1", fn)
    with pytest.raises(Exception):
        g.add("b", os.path.abspath("r/a1"), fn)

    g = create_group("r")
    _p = Path(".").resolve() / "x"
    g.add("a", fn, File(_p))
    with pytest.raises(Exception):
        g.add(_p, fn)

    g = create_group("r")
    _p = Path(".").resolve() / "x"
    g.add("a", fn, VFile(_p))
    with pytest.raises(Exception):
        g.add(_p, fn)

    # zero paths
    with pytest.raises(Exception):
        create_group("r").add("a", (), fn)

    # inconsistent IFile type
    with pytest.raises(Exception):
        create_group("r").add("a", ["a1", VFile("a1")], fn)

    with pytest.raises(Exception):
        create_group("r").addvf("a", "a1", fn, File("r/a1"))

    g = create_group("r")
    g.add("a", fn, File("x"))
    with pytest.raises(Exception):
        g.add("b", fn, VFile("x"))

    # output paths not passed to method
    with pytest.raises(Exception):
        create_group("r").add("a", ["a1", "a2"], fn, SELF[0])

    # args contain an object that lacks pickle-unpickle invariance
    with pytest.raises(Exception):
        create_group("r").add("a", fn, object())

    # unpicklable args
    with pytest.raises(Exception):
        create_group("r").add("a", fn, lambda: 0)


def test_add_by_decorator():
    for adder_name in ["add", "addvf"]:
        g = create_group("r")
        adder = getattr(g, adder_name)

        _fn = adder("a", "a1", None)(fn)
        assert g.a.abspath == Path("r/a1").resolve()
        assert _fn == fn  # decorator should return the func as-is

        _fn = adder("b", None)(fn)
        assert g.b.abspath == Path("r/b").resolve()
        assert _fn == fn


def test_rule_touch(tmp_path):
    r = create_group(tmp_path).add("a", ["a1", "a2"], fn)

    # both
    r.touch(True)
    assert os.path.getmtime(r[0].path) == os.path.getmtime(r[1].path)

    # a1 only
    r.clean()
    r[0].touch(True)
    assert os.path.exists(r[0].path)
    assert not os.path.exists(r[1].path)

    # touch with create=False
    os.utime(r[0].path, (0, 0))
    r.touch()
    assert os.path.getmtime(r[0].path) > 0
    assert not os.path.exists(r[1].path)


def test_rule_clean(tmp_path):
    r = create_group(tmp_path).add("a", ["a1", "a2"], fn)

    # don't raise if file does not exist
    r.clean()

    r.touch(create=True)
    r[1].clean()
    assert os.path.exists(r[0].path)
    assert not os.path.exists(r[1].path)


def test_select_sig1():
    """
    Signature-1: Group.select(group_tree_pattern: str)
    Signature-2: Group.select(group_tree_pattern: Sequence[str], group=False)

    This test is for Signature-1
    """

    """
    a/
    |-- a
    |-- b/
    |   |-- a
    |   |-- a_a
    |   |-- b_a
    |   `-- c/
    |-- c/
    |   |-- a/
    |   |   `-- b/
    |   |       `-- c/
    |   |           `-- d
    |   |-- b/
    |   |   `-- a/
    |   `-- c
    `-- d/
        `-- a
    """
    fn = lambda x: None

    g = create_group("a")
    g.add("a", fn)

    g.add_group("b")
    g.b.add("a", {0: "a"}, fn)
    g.b.add("a_a", fn)
    g.b.add("b_a", fn)
    g.b.add_group("c")

    g.add_group("c")
    g.c.add_group("a").add_group("b").add_group("c").add("d", fn)
    g.c.add_group("b").add_group("a")
    g.c.add("c", fn)

    g.add_group("d").add("a", fn)

    # no *
    assert g.select("a") == [g.a]
    assert g.select("b/") == [g.b]
    assert g.select("b/c/") == [g.b.c]
    assert g.b.select("a") == g.select("b/a")

    # single *
    assert g.select("*") == [g.a]
    assert g.select("*/") == [g.b, g.c, g.d]
    assert g.select("b/*") == [g.b.a, g.b.a_a, g.b.b_a]
    assert g.select("*/a") == [g.b.a, g.d.a]
    assert set(g.select("*/*")) == set([g.b.a, g.c.c, g.d.a, g.b.a_a, g.b.b_a])
    assert g.select("b/*_a") == [g.b.a_a, g.b.b_a]
    assert g.select("b/a*") == [g.b.a, g.b.a_a]
    assert g.select("b/*_*") == [g.b.a_a, g.b.b_a]
    assert g.select("*/a/*/") == [g.c.a.b]
    assert g.select("c/*/*/") == [g.c.a.b, g.c.b.a]
    assert g.c.select("*/*/") == g.select("c/*/*/")

    # double *
    assert set(g.select("**")) == set(
        [g.a, g.b.a, g.c.a.b.c.d, g.c.c, g.d.a, g.b.a_a, g.b.b_a]
    )
    assert g.select("**/") == [
        g,
        g.b,
        g.b.c,
        g.c,
        g.c.a,
        g.c.a.b,
        g.c.a.b.c,
        g.c.b,
        g.c.b.a,
        g.d,
    ]
    assert g.select("**/a") == [g.a, g.b.a, g.d.a]
    assert g.select("c/**/**") == g.select("c/**")
    assert g.select("c/**/**/") == g.select("c/**/")
    assert g.c.select("**/") == g.select("c/**/")

    # misc
    assert g.select("**/*") == g.select("**")
    assert g.select("**/*_a") == [g.b.a_a, g.b.b_a]

    # error
    with pytest.raises(ValueError):
        g.select("")

    with pytest.raises(ValueError):
        g.select("***")

    with pytest.raises(ValueError):
        g.select("**a")

    # names containing parents
    g = create_group("root")
    a = g.add("a/a", fn)
    sub = g.add_group("x/y")
    b = sub.add("b/b/", fn)

    assert g.select("*") == [a]
    assert g.select("**") == [a, b]
    assert g.select("*/") == [sub]
    assert sub.select("*") == [b]


def test_select_sig2():
    """
    Signature-1: Group.select(group_tree_pattern: str)
    Signature-2: Group.select(group_tree_pattern: Sequence[str], group=False)

    This test is for Signature-2.
    Test for Signature-1 is assumed to be succeeded.
    """
    fn = lambda x: None

    g = create_group("root")
    g.add("a1", fn)
    g.add("a2", fn)
    g.add_group("sub")
    g.sub.add("b1", fn)
    g.sub.add("b2", fn)
    g.sub.add_group("sub")

    a = g.add("a/a", fn)
    sub = g.add_group("x/y")
    b = sub.add("b/b/", fn)

    assert g.select(["a1"]) == g.select("a1")
    assert g.select(["sub", "b1"]) == g.select("sub/b1")
    assert g.select(["*"]) == g.select("*")
    assert g.select(["**"]) == g.select("**")
    assert g.select(("*", "*")) == g.select("*/*")
    assert g.select(("**", "*1")) == g.select("**/*1")

    assert g.select(["sub"], True) == g.select("sub/")
    assert g.select(["**"], True) == g.select("**/")

    assert g.select(["a/a"]) == [a]
    assert g.select(["**", "*/*"]) == [a, b]
    assert g.select(["x/y"], True) == [sub]
    assert g.select(["x/y", "*"]) == [b]
