import sys, os, shutil, glob, time
from pathlib import Path
from unittest.mock import patch

import pytest

from jtcmake.core.check_update_result import (
    Necessary,
    PossiblyNecessary,
    UpToDate,
    Infeasible,
)

from jtcmake.rule.rule import Rule

from jtcmake.rule.file import File, VFile, IFile, IFileBase

from jtcmake.rule.memo import IMemo, StrHashMemo


_args = (object(),)
_kwargs = {"a": object()}
_method = lambda: None


def rm(*paths):
    for p in paths:
        if isinstance(p, IFileBase):
            p = p.path
        try:
            os.remove(p)
        except:
            pass


def touch(*paths, t=None):
    if t is None:
        t = time.time()

    for p in paths:
        if isinstance(p, IFileBase):
            p = p.path
        Path(p).touch()
        os.utime(p, (t, t))


def test_metadata_fname(mocker):
    """Rule.metadata_fname is decided based on the name of the first
    output file (p) as follows:
        metadata_fname := p.parent / '.jtcmake' / p.name
    """
    y1, y2 = File(Path("a/b.c")), File(Path("d/e.f"))
    memo = mocker.MagicMock()
    r = Rule([y1, y2], [], [], [], _method, _args, _kwargs, memo)
    assert os.path.abspath(r.metadata_fname) == os.path.abspath(
        "a/.jtcmake/b.c"
    )


def test_update_memo(tmp_path, mocker):
    import pickle

    mock_memo = mocker.MagicMock(IMemo)
    mock_memo.memo = 0

    y1, y2 = File(tmp_path / "f1"), VFile(tmp_path / "f2")
    x1, x2 = (File(tmp_path / f"x{i}") for i in (1, 2))
    ys = [y1, y2]
    xs = [x1, x2]
    xisorig = [True, True]

    r = Rule(ys, xs, xisorig, [], _method, _args, _kwargs, mock_memo)

    r.update_memo()

    mock_memo.save_memo.assert_called_once_with(r.metadata_fname)


def test_rule_check_update(tmp_path, mocker):
    """
    Prerequisite: the y-list has at least one item.

    Procedure:

    - dry run:
        1. Any original x does not exist or has mtime of 0: Infeasible
        2. Any y is missing or has a mtime of 0: Necessary
        3. Any x with IFile type is newer than the oldest y: Necessary
        4. Memoized values are updated: Necessary
        5. Any parent was updated: PossiblyNecessary
        6. Otherwise: UpToDate
    - not dry run
        1. Any x does not exist or has mtime of 0: Infeasible
        2. Any y is missing or has a mtime of 0: Necessary
        3. Any x with IFile type is newer than the oldest y: Necessary
        4. Memoized values are updated: Necessary
        5. ---
        6. Otherwise: UpToDate
    """

    #### multi-y, multi-x, fixed args cases ####

    y1, y2 = File(tmp_path / "y1"), VFile(tmp_path / "y2")
    x1, x2 = File(tmp_path / "x1"), VFile(tmp_path / "x2")

    ys = [y1, y2]
    xs = [x1, x2]
    xisorig = [True, True]

    def _Rule(ys, xs, xisorig, memo_no_change):
        mock_memo = mocker.MagicMock(IMemo)
        mock_memo.compare_to_saved.return_value = memo_no_change
        mock_memo.memo = 0

        return Rule(ys, xs, xisorig, [], lambda x: None, [], {}, mock_memo)

    # case 1 (dry_run, x1 is original)
    r = _Rule([y1, y2], [x1, x2], [True, False], True)

    # x1 (original) is missing
    rm(x1)
    touch(x2, y1, y2)
    assert isinstance(r.check_update(False, True), Infeasible)

    # x1's mtime is 0
    touch(y1, y2, x2)
    touch(x1, t=0)
    assert isinstance(r.check_update(False, True), Infeasible)

    # case 1 (not dry_run)
    r = _Rule([y1, y2], [x1, x2], [False, False], True)

    # x1 (original) is missing
    rm(x1)
    touch(x2, y1, y2)
    assert isinstance(r.check_update(False, False), Infeasible)

    # x1's mtime is 0
    touch(y1, y2, x2)
    touch(x1, t=0)
    assert isinstance(r.check_update(False, False), Infeasible)

    # case 2
    r = _Rule([y1, y2], [x1, x2], [False, False], True)

    for dry_run in (False, True):
        # y1 is missing
        rm(y1)
        touch(x1, x2, y2)
        assert isinstance(r.check_update(False, dry_run), Necessary)

        # y1 has mtime of 0
        touch(y2)
        touch(y1, t=0)
        assert isinstance(r.check_update(False, dry_run), Necessary)

    # case 3 (x1 is newer than y2)
    r = _Rule([y1, y2], [x1, x2], [False, False], True)

    for dry_run in (False, True):
        t = time.time()
        touch(x2, t=t - 3)
        touch(y2, t=t - 2)
        touch(x1, t=t - 1)
        touch(y1, t=t - 0)
        assert isinstance(r.check_update(False, dry_run), Necessary)

    # case 4
    r = _Rule([y1, y2], [x1, x2], [False, False], False)

    for dry_run in (False, True):
        touch(y1, y2, x1, x2)
        assert isinstance(r.check_update(False, dry_run), Necessary)

    # case 5 (dry_run)
    r = _Rule([y1, y2], [x1, x2], [False, True], True)

    touch(x1, x2, y1, y2)
    assert isinstance(r.check_update(True, True), PossiblyNecessary)

    touch(x2, y1, y2)
    touch(x1, t=0)
    assert isinstance(r.check_update(True, True), PossiblyNecessary)

    touch(x2, y1, y2)
    rm(x1)
    assert isinstance(r.check_update(True, True), PossiblyNecessary)

    # case 6
    r = _Rule([y1, y2], [x1, x2], [True, False], True)
    for dry_run in (False, True):
        t = time.time()
        # input IVFile is newer than output files
        touch(x1, t=t - 2)
        touch(y1, t=t - 1)
        touch(y2, t=t - 1)
        touch(x2, t=t - 0)
        assert isinstance(r.check_update(False, dry_run), UpToDate)

        # equal mtime
        touch(y1, y2, x1, x2)
        assert isinstance(r.check_update(False, dry_run), UpToDate)

    # pass case 5 with !dry_run
    touch(x1, x2, y1, y2)
    assert isinstance(r.check_update(True, False), UpToDate)

    #### no x ####
    r = _Rule([y1, y2], [], [], True)

    # case 6.
    for dry_run in (False, True):
        touch(y1, y2)
        assert isinstance(r.check_update(False, dry_run), UpToDate)


def test_preprocess(tmp_path, mocker):
    """Rule.preprocess(callaback) should make dirs for all its output files."""
    mock_memo = mocker.MagicMock(IMemo)
    y = File(tmp_path / "a")
    r = Rule([y], [], [], [], _method, _args, _kwargs, mock_memo)
    r.preprocess(lambda *_: None)
    assert os.path.exists(y.path.parent)
    assert os.path.isdir(y.path.parent)


def test_postprocess(tmp_path, mocker):
    """Rule.postprocess(callback, successed:bool) should
    1. if successed,
        1. update memo
    2. if !successed,
        1. Set mtime of all the existing output files to 0
        2. Delete memo
    """
    mock_memo = mocker.MagicMock(IMemo)

    y = File(tmp_path / "y")
    x1 = File(tmp_path / "x1")
    x2 = VFile(tmp_path / "x2")
    xisorig = [True, True]

    r = Rule([y], [x1, x2], xisorig, [], _method, _args, _kwargs, mock_memo)

    touch(x1, x2)
    r.postprocess(lambda *_: None, True)

    mock_memo.save_memo.assert_called_once_with(r.metadata_fname)

    # TODO: test
