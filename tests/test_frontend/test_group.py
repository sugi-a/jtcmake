import sys, os, shutil, glob, time, inspect
from pathlib import Path, PurePath
from typing import Sequence

import pytest

from jtcmake.frontend.group import create_group, SELF, Group, Rule as RuleNode
from jtcmake.rule.file import File, VFile, IFile
from jtcmake.rule.rule import Rule as _RawRule
from jtcmake.utils.nest import map_structure
import jtcmake


class _PathLike:
    def __init__(self, p):
        self.p = str(p)

    def __fspath__(self):
        return self.p


fn = lambda *x, **y: None


def test_create_group():
    g = create_group("root")
    assert isinstance(g, Group)

    g = create_group(prefix="root")
    assert isinstance(g, Group)

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


def test_add_group_invalid_calls():
    # argument type errors
    with pytest.raises(Exception):
        create_group("r").add(1, fn, SELF)

    with pytest.raises(Exception):
        create_group("r").add("a", 1, fn, SELF)

    with pytest.raises(Exception):
        create_group("r").add("a", "a", 1)

    # name being empty str
    with pytest.raises(Exception):
        create_group("root").add("", "a", fn, SELF)

    # overwriting
    g = create_group("r")
    g.add("a", fn, SELF)
    with pytest.raises(Exception):
        g.add("a", fn, SELF)

    # path collision
    g = create_group("r")
    g.add("a", "a1", fn, SELF)
    with pytest.raises(Exception):
        g.add("b", os.path.abspath("r/a1"), fn, SELF)

    g = create_group("r")
    _p = Path(os.path.abspath("x"))
    g.add("a", fn, File(_p), SELF)
    with pytest.raises(Exception):
        g.add(_p, fn, SELF)

    g = create_group("r")
    _p = Path(os.path.abspath("x"))
    g.add("a", fn, VFile(_p), SELF)
    with pytest.raises(Exception):
        g.add(_p, fn, SELF)

    # zero paths
    with pytest.raises(Exception):
        create_group("r").add("a", (), fn, SELF)

    # inconsistent IFile type
    with pytest.raises(Exception):
        create_group("r").add("a", {"a": "a", "b": VFile("a")}, fn, SELF.a1)

    with pytest.raises(Exception):
        create_group("r").addvf("a", "a1", fn, File("r/a1"), SELF)

    g = create_group("r")
    g.add("a", fn, File("x"), SELF)
    with pytest.raises(Exception):
        g.add("b", fn, VFile("x"), SELF)

    # output paths not passed to method
    with pytest.raises(Exception):
        create_group("r").add("a", ["a1", "a2"], fn, SELF.a1)

    # args contain an object that lacks pickle-unpickle invariance
    with pytest.raises(Exception):
        create_group("r").add("a", fn, SELF, object())

    # unpicklable args
    with pytest.raises(Exception):
        create_group("r").add("a", fn, SELF, lambda: 0)

    # arguments shape not matching the method signature
    with pytest.raises(TypeError):
        create_group("r").add("a", lambda x: None, SELF, 1)


"""
_Group = {
    _rules?: { [str]: _RuleNode }
    _files?: { [str]: _File }[]
    _groups?: { [str]: _Group }[]
}
_RuleNode = {
    _rule: _RawRule
}
_RawRule = {
    args?: (Any, ...)
    kwargs?: { [str]: Any }
}
_File = IFile
"""


def _assert_group(ref, out):
    assert isinstance(out, Group)

    if "_rules" in ref:
        assert set(ref["_rules"]) == set(out._rules)
        for k, v in ref["_rules"].items():
            _assert_rule_node(v, out._rules[k])

    if "_files" in ref:
        assert set(ref["_files"]) == set(out._files)
        for k, v in ref["_files"].items():
            _assert_file(v, out._files[k])

    if "_groups" in ref:
        assert set(ref["_groups"]) == set(out._groups)
        for k, v in ref["_groups"].items():
            _assert_group(v, out._groups[k])


def _assert_rule_node(ref, out):
    assert isinstance(out, RuleNode)

    if isinstance(ref, RuleNode):
        assert ref == out
        return

    assert isinstance(ref, dict)

    if "_rule" in ref:
        _assert_rule(ref["_rule"], out._rule)


def _assert_rule(ref, out):
    assert isinstance(out, _RawRule)

    if "args" in ref:
        assert ref["args"] == out.args

    if "kwargs" in ref:
        assert ref["kwargs"] == out.kwargs


def _assert_file(ref, out):
    assert isinstance(out, IFile)
    assert type(ref) == type(out)
    assert os.path.abspath(ref) == os.path.abspath(out)


@pytest.mark.parametrize("method", ["add", "addvf"])
@pytest.mark.parametrize("name", [None, "name"])
@pytest.mark.parametrize("use_abs", [False, True])
@pytest.mark.parametrize("out_type", [str, Path, File, VFile])
@pytest.mark.parametrize("out_shape", ["atom", "dict", "list"])
@pytest.mark.parametrize("deco", [False, True])
# @pytest.mark.parametrize(
#    "method,name,use_abs,out_type,out_shape",
#    [("addvf", "name", False, str, "dict")]
# )
def test_add_basic(mocker, method, name, use_abs, out_type, out_shape, deco):
    _fn = lambda *args, **kwargs: None

    mock_add = mocker.patch("jtcmake.frontend.group.Group._add")

    g = create_group("g")
    method_ = getattr(g, method)

    _to_abs = os.path.abspath if use_abs else lambda x: x

    def _default_file(v):
        if isinstance(v, IFile):
            return v
        else:
            return File(v) if method == "add" else VFile(v)

    if out_shape == "dict":
        outs = {"b": _to_abs(out_type("B")), "a": _to_abs(out_type("A"))}
        ref_name = name or "b"
        ref_outs = {k: _default_file(v) for k, v in outs.items()}
    elif out_shape == "list":
        outs = [_to_abs(out_type("A")), _to_abs(out_type("B"))]
        ref_name = name or str(outs[0])
        ref_outs = {str(v): _default_file(v) for v in outs}
    elif out_shape == "atom":
        outs = _to_abs(out_type("A"))
        ref_name = name or str(outs)
        ref_outs = {str(outs): _default_file(outs)}
    else:
        raise Exception()

    if name is None:
        method__ = method_
    else:
        method__ = lambda *args, **kwargs: method_(name, *args, **kwargs)

    if deco:
        method__(outs, None, 1, a=2)(_fn)
    else:
        method__(outs, _fn, 1, a=2)

    mock_add.assert_called_once_with(ref_name, ref_outs, _fn, [1], {"a": 2})


@pytest.mark.parametrize("ftype", [File, VFile])
@pytest.mark.parametrize("use_abs", [False, True])
def test__add_basic(mocker, ftype, use_abs):
    _fn = lambda *args, **kwargs: None
    _to_abs = os.path.abspath if use_abs else lambda x: x
    _ref_to_abs = os.path.abspath if use_abs else lambda x: "g/" + x

    def _assert_eq_path(x, y):
        if isinstance(x, Path):
            x = Path(os.path.abspath(x))
        if isinstance(y, Path):
            y = Path(os.path.abspath(y))
        assert x == y

    def _assert_eq_path_strict(x, y):
        if isinstance(x, Path):
            assert type(x) == type(y)
            assert x == y
        else:
            assert x == y

    _rule_call_params = None

    def _set_rule_call_params(*args, **kwargs):
        nonlocal _rule_call_params
        _rule_call_params = (args, kwargs)
        return _RawRule(*args, **kwargs)

    g = create_group("g")

    mock__rule = mocker.patch(
        "jtcmake.frontend.group._RawRule", side_effect=_set_rule_call_params
    )

    node_a = g._add(
        "name_a",
        {"a": ftype(_to_abs("a.txt"))},
        _fn,
        (SELF, 1, [{1: (SELF,)}]),
        {"a": 2, "b": SELF},
    )

    _assert_group(
        {
            "_rules": {"name_a": node_a},
            "_files": {"a": ftype(_ref_to_abs("a.txt"))},
            "_group": {},
        },
        g,
    )

    mock__rule.assert_called_once()

    _params = (
        inspect.signature(_RawRule)
        .bind(*_rule_call_params[0], **_rule_call_params[1])
        .arguments
    )

    print(_params)

    map_structure(_assert_eq_path_strict, _params["yfiles"], [g._files.a])

    assert _params["xfiles"] == []
    assert _params["xfile_is_orig"] == []
    assert _params["deplist"] == set()
    assert _params["method"] == _fn

    map_structure(
        _assert_eq_path,
        (_params["args"], _params["kwargs"]),
        ((g._files.a, 1, [{1: (g._files.a,)}]), {"a": 2, "b": g._files.a}),
    )

    mock__rule = mocker.patch(
        "jtcmake.frontend.group._RawRule", side_effect=_set_rule_call_params
    )

    node_b = g._add(
        "name_b", {"b": ftype("b.txt")}, _fn, (SELF, g.F.a, File("c.txt")), {}
    )

    _assert_group(
        {
            "_rules": {"name_a": node_a, "name_b": node_b},
            "_files": {
                "a": ftype(_ref_to_abs("a.txt")),
                "b": ftype("g/b.txt"),
            },
            "_group": {},
        },
        g,
    )

    mock__rule.assert_called_once()

    _params = (
        inspect.signature(_RawRule)
        .bind(*_rule_call_params[0], **_rule_call_params[1])
        .arguments
    )

    map_structure(_assert_eq_path_strict, _params["yfiles"], [g._files.b])
    map_structure(
        _assert_eq_path_strict, _params["xfiles"], [g._files.a, File("c.txt")]
    )
    assert _params["xfile_is_orig"] == [False, True]
    assert _params["deplist"] == {0}
    map_structure(
        _assert_eq_path,
        (_params["args"], _params["kwargs"]),
        ((g._files.b, g._files.a, Path("c.txt")), {}),
    )


def test__add_posix_path_expansion():
    if os.name == "nt":
        return

    _fn = lambda *args, **kwargs: None
    g = create_group("g")
    g._add("name", {"a": File("~/a")}, _fn, (SELF,), {})

    _assert_group({"_files": {"a": File(os.path.expanduser("~/a"))}}, g)


def test_rule_touch(tmp_path):
    r = create_group(tmp_path).add("a", ["a1", "a2"], fn, SELF.a1, SELF.a2)

    r.touch(True)
    assert os.path.getmtime(r.a1) == os.path.getmtime(r.a2)

    # touch with create=False
    os.remove(r.a2)
    os.utime(r.a1, (0, 0))
    r.touch()
    assert os.path.getmtime(r.a1) > 0
    assert not os.path.exists(r.a2)


def test_rule_clean(tmp_path):
    r = create_group(tmp_path).add("a", ["a1", "a2"], fn, SELF.a1, SELF.a2)

    # don't raise if file does not exist
    r.clean()

    r.touch(create=True)

    r.clean()
    assert not os.path.exists(r.a1)
    assert not os.path.exists(r.a2)


@pytest.mark.parametrize("kind", ["group", "rule", "file"])
def test_group_select(mocker, kind):
    m = mocker.patch("jtcmake.frontend.group.Group._select_wrapper")

    g = create_group("g")
    getattr(g, f"select_{kind}s")("a")

    m.assert_called_once_with("a", kind)


@pytest.mark.parametrize("kind", ["group", "rule", "file"])
@pytest.mark.parametrize(
    "x,y",
    [
        ("a", ["a"]),
        ("a/b/**/*c", ["a", "b", "**", "*c"]),
        ("/a/b/", ["a", "b"]),
        (["a", "b/c", "**"], None),
    ],
)
def test_group__select_wrapper(mocker, x, y, kind):
    m = mocker.patch("jtcmake.frontend.group.Group._select")

    y = y or x

    g = create_group("g")
    g._select_wrapper(x, kind)

    m.assert_called_once_with(y, kind)


def _create_group_for_test_select():
    """
    a/
    |-- a (a)
    |-- b (b, c)
    |-- a/
    |   |-- a (a)
    |   |-- a/
    |   `-- a/b (a/b)
    |-- b/
    |   `-- a/
    `-- a/b/
        `-- a (a_)
    """
    _fn = lambda *args, **kwargs: None

    g = create_group("g")
    g.add_group("a")
    g.a.add_group("a")
    g.a.add_group("a/b")

    g.add_group("b")
    g.b.add_group("a")

    g.add_group("a/b")

    g.add("a", _fn, SELF)
    g.add("b", ["b", "c"], _fn, SELF.b, SELF.c)

    g.a.add("a", _fn, SELF)
    g.a.add("a/b", _fn, SELF)

    g.G["a/b"].add("a", _fn, SELF)

    return g


def test_group_select_groups():
    g = _create_group_for_test_select()
    # no *
    assert g.select_groups("a") == [g.a]
    assert g.select_groups("b/a") == [g.b.a]
    assert g.b.select_groups("a") == g.select_groups("b/a")

    # *
    assert set(g.select_groups("*")) == {g.a, g.b, g.G["a/b"]}
    assert g.select_groups("b/*") == [g.b.a]
    assert set(g.select_groups("*/a")) == {g.a.a, g.b.a}
    assert set(g.select_groups("*/*")) == {g.a.a, g.a.G["a/b"], g.b.a}

    # **
    assert set(g.select_groups("**")) == {
        g,
        g.a,
        g.a.a,
        g.a.G["a/b"],
        g.b,
        g.b.a,
        g.G["a/b"],
    }

    assert set(g.select_groups("**/a")) == {g.a, g.a.a, g.b.a}
    assert set(g.select_groups("**/a")) == {g.a, g.a.a, g.b.a}


def test_group_select_rules():
    g = _create_group_for_test_select()
    # no *
    assert g.select_rules("a") == [g.R.a]

    # *
    assert set(g.select_rules("*")) == {g.R.a, g.R.b}

    # **
    assert set(g.select_rules("**")) == {
        g.R.a,
        g.R.b,
        g.a.R.a,
        g.a.R["a/b"],
        g.G["a/b"].R.a,
    }


def test_group_select_files():
    g = _create_group_for_test_select()
    # no *
    assert g.select_files("c") == [g.F.c]

    # *
    assert set(g.select_files("*")) == {g.F.a, g.F.b, g.F.c}


@pytest.mark.parametrize(
    "method", ["select_groups", "select_rules", "select_files"]
)
def test_group_select_common(method):
    def _method(g):
        return getattr(g, method)

    g = _create_group_for_test_select()

    assert set(_method(g)("**/**")) == set(_method(g)("**"))

    # error
    with pytest.raises(ValueError):
        _method(g)("")

    with pytest.raises(ValueError):
        _method(g)("***")

    with pytest.raises(ValueError):
        _method(g)("**a")
