import os
import time
from pathlib import Path
from typing import Any, Optional, Union

import pytest

from jtcmake import raw_rule
from jtcmake.core.abc import UpdateResults
from jtcmake.raw_rule import IMemo, Rule

Necessary = UpdateResults.Necessary
PossiblyNecessary = UpdateResults.PossiblyNecessary
UpToDate = UpdateResults.UpToDate
Infeasible = UpdateResults.Infeasible


def _method():
    return None


StrOrPath = Union[str, "os.PathLike[str]"]

NoneType = type(None)


def rm(*paths: StrOrPath):
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass


def touch(*paths: StrOrPath, t: Optional[float] = None):
    if t is None:
        t = time.time()

    for p in paths:
        Path(p).touch()
        os.utime(p, (t, t))


def _Path():
    def create(p: StrOrPath):
        return Path(p)

    return create


def EPath(relt: Optional[float] = None):
    def create(path: StrOrPath):
        p = Path(path)
        t = time.time() + (relt or 0)
        p.touch()
        os.utime(p, (t, t))
        return p

    return create


def E0Path():
    def create(path: StrOrPath):
        p = Path(path)
        p.touch()
        os.utime(p, (0, 0))
        return p

    return create


class Memo(IMemo):
    """Fake object to represent IMemo"""

    res: bool

    def __init__(self, res: bool):
        self.res = res

    def compare(self):
        return self.res

    def update(self):
        ...


"""
Prerequisite: the y-list has at least one item.

Procedure:

- dry run:
    1. dry_run?
        yes: Any original x does not exist or has mtime of 0: Infeasible
        no:  Any x does not exist or has mtime of 0: Infeasible
    2. Any y is missing or has a mtime of 0: Necessary
    3. dry_run and any parent was updated: PossiblyNecessary
    4. Any x of type File is newer than the oldest y: Necessary
    5. Memoized values are updated: Necessary
    6. Otherwise: UpToDate
"""


@pytest.mark.parametrize(
    "xs,xisorig,expect",
    [
        ([Path, EPath()], [True, False], Infeasible),
        ([E0Path(), EPath()], [True, False], Infeasible),
        ([EPath(), EPath()], [False, False], NoneType),
        ([Path, EPath()], [False, False], NoneType),
    ],
)
def test_check_update_1_dryrun(
    tmp_path: Path, xs: Any, xisorig: Any, expect: Any
):
    func = raw_rule._check_update_1  # pyright: ignore [reportPrivateUsage]
    xs = [v(tmp_path / str(i)) for i, v in enumerate(xs)]
    assert isinstance(func(xs, xisorig, True), expect)


@pytest.mark.parametrize("isorig1", [True, False])
@pytest.mark.parametrize("isorig2", [True, False])
@pytest.mark.parametrize(
    "xs,expect",
    [
        ([Path, EPath()], Infeasible),
        ([E0Path(), EPath()], Infeasible),
        ([EPath(), EPath()], NoneType),
    ],
)
def test_check_update_1_nodryrun(
    tmp_path: Path, xs: Any, isorig1: Any, isorig2: Any, expect: Any
):
    func = raw_rule._check_update_1  # pyright: ignore [reportPrivateUsage]
    xs = [v(tmp_path / str(i)) for i, v in enumerate(xs)]
    assert isinstance(func(xs, [isorig1, isorig2], False), expect)


@pytest.mark.parametrize(
    "ys,expect",
    [
        ([Path, EPath()], Necessary),
        ([E0Path(), EPath()], Necessary),
        ([EPath(), EPath()], NoneType),
    ],
)
def test_check_update_2(tmp_path: Path, ys: Any, expect: Any):
    func = raw_rule._check_update_2  # pyright: ignore [reportPrivateUsage]
    ys = [v(tmp_path / str(i)) for i, v in enumerate(ys)]
    assert isinstance(func(ys), expect)


@pytest.mark.parametrize(
    "dry_run,par_updated,expect",
    [
        (True, True, PossiblyNecessary),
        (False, True, NoneType),
        (True, False, NoneType),
        (False, False, NoneType),
    ],
)
def test_check_update_3(dry_run: Any, par_updated: Any, expect: Any):
    func = raw_rule._check_update_3  # pyright: ignore [reportPrivateUsage]
    assert isinstance(func(dry_run, par_updated), expect)


@pytest.mark.parametrize(
    "ys,xs,xisvf,expect",
    [
        ([EPath(), EPath()], [EPath(1), EPath(-1)], [False, False], Necessary),
        ([EPath(), EPath()], [EPath(1), EPath(-1)], [True, False], NoneType),
        ([EPath(), EPath()], [EPath(-1), EPath(-1)], [False, False], NoneType),
    ],
)
def test_check_update_4(
    tmp_path: Path, xs: Any, ys: Any, xisvf: Any, expect: Any
):
    func = raw_rule._check_update_4  # pyright: ignore [reportPrivateUsage]
    xs = [v(tmp_path / f"a{i}") for i, v in enumerate(xs)]
    ys = [v(tmp_path / f"b{i}") for i, v in enumerate(ys)]
    assert isinstance(func(ys, xs, xisvf), expect)


@pytest.mark.parametrize(
    "memo,expect",
    [
        (Memo(False), Necessary),
        (Memo(True), NoneType),
    ],
)
def test_check_update_5(memo: Any, expect: Any):
    func = raw_rule._check_update_5  # pyright: ignore [reportPrivateUsage]
    assert isinstance(func(memo), expect)


def test_preprocess(tmp_path: Path, mocker: Any):
    """Rule.preprocess(callaback) should make dirs for all its output files."""
    mock_memo = mocker.MagicMock(IMemo)
    y = tmp_path / "a"
    r = Rule([y], [], [], [], set(), _method, mock_memo, 0)

    r.preprocess()
    assert os.path.exists(y.parent)
    assert os.path.isdir(y.parent)


def test_postprocess(tmp_path: Path, mocker: Any):
    """Rule.postprocess(callback, successed:bool) should
    1. if successed,
        1. update memo
    2. if !successed,
        1. Set mtime of all the existing output files to 0
        2. Delete memo
    """
    mock_memo = mocker.MagicMock(IMemo)

    y = tmp_path / "y"
    x1 = tmp_path / "x1"
    x2 = tmp_path / "x2"
    xisorig = [True, True]

    def meth():
        ...

    r = Rule([y], [x1, x2], xisorig, [True, False], set(), meth, mock_memo, 0)

    touch(y, x1, x2)

    r.postprocess(True)

    mock_memo.update.assert_called_once()


def test_postprocess_fail_missing_yfile(tmp_path: Path, mocker: Any):
    mock_memo = mocker.MagicMock(IMemo)

    y = tmp_path / "y"
    x1 = tmp_path / "x1"
    x2 = tmp_path / "x2"
    xisorig = [True, True]

    def meth():
        ...

    r = Rule([y], [x1, x2], xisorig, [True, False], set(), meth, mock_memo, 0)

    with pytest.raises(FileNotFoundError):
        r.postprocess(True)
