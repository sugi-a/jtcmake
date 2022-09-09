import sys, os, shutil, glob, time
from pathlib import Path, PurePath

import pytest

from jtcmake import create_group, SELF, MakeSummary
import jtcmake


def touch(*dst):
    for p in dst:
        Path(p).touch()


def add_text(dst, src, text=None, t=0):
    src = "" if src is None else Path(src).read_text()
    text = "" if text is None else text

    if t > 0:
        time.sleep(t)

    Path(dst).write_text(src + text)


def cp_1_to_n(dsts, src):
    for d in dsts:
        shutil.copy(src, d)


def cp_n_to_1(dst, srcs):
    Path(dst).write_text("".join(Path(s).read_text() for s in srcs))


def globfiles(dirname):
    ps = glob.iglob(f"{dirname}/**", recursive=True)
    ps = [os.path.relpath(p, dirname) for p in ps if os.path.isfile(p)]
    ps.sort()
    return ps


@pytest.mark.parametrize("njobs", [None, 1, 2, 3])
def test_1(njobs, tmp_path):
    """basics"""

    g = create_group(tmp_path)

    g.add("a", "a.txt", add_text, None, "a")
    g.add("aa", "aa.txt", add_text, SELF, g.a, "a")

    @g.add("aaa", "aaa.txt", None, g.aa)
    def _(dst, src):
        add_text(dst, src, "a")

    g1 = g.add_group("g1", "g1/")
    g1.add("ab", "ab.txt", add_text, g.a, "b")

    # dry-run
    res = g.make(dry_run=True, njobs=njobs)

    assert res == MakeSummary(total=4, update=4, skip=0, fail=0, discard=0)
    assert globfiles(tmp_path) == []

    # run all
    res = g.make(njobs=njobs)

    assert res == MakeSummary(total=4, update=4, skip=0, fail=0, discard=0)

    # make sure to deal with windows path \\
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ["a.txt", "aa.txt", "aaa.txt", "g1/ab.txt"]
    )
    assert Path(g.aaa.path).read_text() == "aaa"

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    res = g.g1.ab.make(njobs=njobs)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ["a.txt", "g1/ab.txt"]
    )

    # run rest
    mt = os.path.getmtime(g.a.path)
    res = g.make(njobs=njobs)

    assert res == MakeSummary(total=4, update=2, skip=2, fail=0, discard=0)
    assert os.path.getmtime(g.a.path) == mt
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ["a.txt", "aa.txt", "aaa.txt", "g1/ab.txt"]
    )

    # clean some
    g.a.clean()
    g.g1.clean()
    assert globfiles(tmp_path) == sorted(["aa.txt", "aaa.txt"])


def test_2(tmp_path):
    # nested path and args
    g = create_group(tmp_path)

    g.add("a", "a.txt", add_text, None, "a")
    g.add(
        "b", ("b1.txt", {"x": "b2.txt"}), cp_1_to_n, [SELF[0], SELF[1].x], g.a
    )
    g.add("c", "c.txt", add_text, g.b[0], "a")

    # run
    g.make()
    assert globfiles(tmp_path) == sorted(
        ["a.txt", "b1.txt", "b2.txt", "c.txt"]
    )


def test_4(tmp_path):
    def fail(*args, **kwargs):
        raise Exception("FAIL")

    # make failure
    g = create_group(tmp_path)

    g.add("a", "a.txt", touch)
    g.add("b1", "b1.txt", fail, g.a)
    g.add("b2", "b2.txt", add_text, g.a, t=1)
    g.add("c1", "c1.txt", add_text, g.b1)
    g.add("c2", "c2.txt", add_text, g.b2)

    # make (don't stop on fail)
    res = g.make(keep_going=True)

    assert res == MakeSummary(total=5, update=3, skip=0, fail=1, discard=1)
    assert globfiles(tmp_path) == sorted(["a.txt", "b2.txt", "c2.txt"])

    g.clean()

    # make (don't stop on fail; multi-thread)
    res = g.make(keep_going=True, njobs=2)

    assert res == MakeSummary(total=5, update=3, skip=0, fail=1, discard=1)
    assert globfiles(tmp_path) == sorted(["a.txt", "b2.txt", "c2.txt"])

    g.clean()
    assert globfiles(tmp_path) == []


def test_addvf(tmp_path):
    from jtcmake import Atom

    _cnt = 0

    def _create_group(x, y):
        nonlocal _cnt
        _cnt += 1

        g = create_group(tmp_path)
        g.addvf("a", lambda p, _: p.write_text(x), _cnt)
        g.add("b", lambda p, _: p.write_text(y), g.a)
        return g

    g = _create_group("0", "0")
    g.make()
    assert (tmp_path / "b").read_text() == "0"

    # if x has been modified, y must be updated
    time.sleep(0.01)
    g = _create_group("1", "1")
    res = g.make()

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert (tmp_path / "b").read_text() == "1"

    # when x was not modified, y must not be updated
    time.sleep(0.01)
    g = _create_group("1", "2")
    res = g.make()

    assert res == MakeSummary(total=2, update=1, skip=1, fail=0, discard=0)
    assert (tmp_path / "b").read_text() == "1"


@pytest.mark.parametrize(
    "memo_kind,pickle_key", [("str_hash", None), ("pickle", "FFFF")]
)
def test_memoization_common(tmp_path, memo_kind, pickle_key):
    """test memoization behavior that is common to 'pickle' and 'str_hash'"""

    def _write(p, t):
        p.write_text(repr(t))

    #### str case ('abc' -> 'def') ####
    before, after = "abc", "def"

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.a.path.read_text() == repr(after)

    #### set case ({1, 2} -> {2, 3}) ####
    before, after = {1, 2}, {2, 3}

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.a.path.read_text() == repr(after)

    #### PurePath/Path case (don't update) (PurePath -> Path) ####
    before, after = PurePath("a"), Path("a")

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.a.path.read_text() == repr(before)

    #### ignore change using Atom(_, None) ({1, 2} -> {2, 3}) ####
    before, after = {1, 2}, {2, 3}

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, jtcmake.Atom(before, None))
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, jtcmake.Atom(before, None))
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.a.path.read_text() == repr(before)  # not after

    #### raise when given instances that are not value object ####
    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)

    with pytest.raises(Exception):
        g.add("a", _write, lambda _: None)

    with pytest.raises(Exception):
        g.add("a", _write, object())


def test_memoization(tmp_path):
    def fn(*args):
        ...

    # str_hash does not support functions, and classes
    g = create_group(tmp_path)

    with pytest.raises(Exception):
        g.add("a", fn, print)

    with pytest.raises(Exception):
        g.add("a", fn, int)

    # pickle supports top level funcs and classes
    g = create_group(tmp_path, memo_kind="pickle", pickle_key="FF")
    g.add("a", fn, print)
    g.add("b", fn, int)


def test_pickle_memo_auth(tmp_path):
    def _write(p, t):
        p.write_text(repr(t))

    KEY1 = b"abc".hex()
    KEY2 = b"xyz".hex()

    g = create_group(tmp_path, memo_kind="pickle", pickle_key=KEY1)
    g.add("a", _write, "a")
    g.make()

    g = create_group(tmp_path, memo_kind="pickle", pickle_key=KEY2)
    g.add("a", _write, "b")
    res = g.make()

    # fail (error on checking update)
    assert res == MakeSummary(total=1, update=0, skip=0, fail=1, discard=0)
