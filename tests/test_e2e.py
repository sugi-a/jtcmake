import sys, os, shutil, glob, time
from pathlib import Path, PurePath

import pytest

from jtcmake import create_group, SELF, MakeSummary, Atom
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


@pytest.mark.parametrize("njobs", [None, 1, 3])
def test_1(njobs, tmp_path):
    """basics"""

    g = create_group(tmp_path)
    files = g.F

    g.add({"a": "a.txt"}, add_text, SELF, None, "a")
    g.add({"aa": "aa.txt"}, add_text, SELF, files.a, "a")

    @g.add({"aaa": "aaa.txt"}, None, SELF, files.aa)
    def _(dst, src):
        add_text(dst, src, "a")

    g1 = g.add_group("g1", "g1/")
    g1.add({"ab": "ab.txt"}, add_text, SELF, files.a, "b")

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
    assert Path(files.aaa).read_text() == "aaa"

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    res = g.g1.R.ab.make(njobs=njobs)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ["a.txt", "g1/ab.txt"]
    )

    # run rest
    mt = os.path.getmtime(files.a)
    res = g.make(njobs=njobs)

    assert res == MakeSummary(total=4, update=2, skip=2, fail=0, discard=0)
    assert os.path.getmtime(files.a) == mt
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ["a.txt", "aa.txt", "aaa.txt", "g1/ab.txt"]
    )

    # clean some
    g.R.a.clean()
    g1.clean()
    assert globfiles(tmp_path) == sorted(["aa.txt", "aaa.txt"])


def test_4(tmp_path):
    def fail(*args, **kwargs):
        raise Exception("FAIL")

    # make failure
    g = create_group(tmp_path)
    files = g.F

    g.add({"a": "a.txt"}, touch, SELF)
    g.add({"b1": "b1.txt"}, fail, SELF, files.a)
    g.add({"b2": "b2.txt"}, add_text, SELF, files.a, t=1)
    g.add({"c1": "c1.txt"}, add_text, SELF, files.b1)
    g.add({"c2": "c2.txt"}, add_text, SELF, files.b2)

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
    _cnt = 0

    def _create_group(x, y):
        nonlocal _cnt
        _cnt += 1

        g = create_group(tmp_path)
        g.addvf("a", lambda p, _: p.write_text(x), SELF, _cnt)
        g.add("b", lambda p, _: p.write_text(y), SELF, g.F.a)
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
    g.add("a", _write, SELF, before)
    g.make()

    assert g.F.a.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.F.a.read_text() == repr(after)

    #### set case ({1, 2} -> {2, 3}) ####
    before, after = {1, 2}, {2, 3}

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, before)
    g.make()

    assert g.F.a.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.F.a.read_text() == repr(after)

    #### PurePath/Path case (don't update) (PurePath -> Path) ####
    before, after = PurePath("a"), Path("a")

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, before)
    g.make()

    assert g.F.a.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.F.a.read_text() == repr(before)

    #### ignore change using Atom(_, None) ({1, 2} -> {2, 3}) ####
    before, after = {1, 2}, {2, 3}

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, g.memnone(before))
    g.make()

    assert g.F.a.read_text() == repr(before)

    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)
    g.add("a", _write, SELF, g.memnone(before))
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.F.a.read_text() == repr(before)  # not after

    #### raise when given instances that are not value object ####
    g = create_group(tmp_path, memo_kind=memo_kind, pickle_key=pickle_key)

    with pytest.raises(Exception):
        g.add("a", _write, SELF, lambda _: None)

    with pytest.raises(Exception):
        g.add("a", _write, SELF, object())


def test_memoization(tmp_path):
    def fn(*args):
        ...

    # str_hash does not support functions, and classes
    g = create_group(tmp_path)

    with pytest.raises(Exception):
        g.add("a", fn, SELF, print)

    with pytest.raises(Exception):
        g.add("a", fn, SELF, int)

    # pickle supports top level funcs and classes
    g = create_group(tmp_path, memo_kind="pickle", pickle_key="FF")
    g.add("a", fn, SELF, print)
    g.add("b", fn, SELF, int)


def test_pickle_memo_auth(tmp_path):
    def _write(p, t):
        p.write_text(repr(t))

    KEY1 = b"abc".hex()
    KEY2 = b"xyz".hex()

    g = create_group(tmp_path, memo_kind="pickle", pickle_key=KEY1)
    g.add("a", _write, SELF, "a")
    g.make()

    g = create_group(tmp_path, memo_kind="pickle", pickle_key=KEY2)
    g.add("a", _write, SELF, "b")
    res = g.make()

    # fail (error on checking update)
    assert res == MakeSummary(total=1, update=0, skip=0, fail=1, discard=0)
