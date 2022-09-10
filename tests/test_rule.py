import sys, os, shutil, glob, time
from pathlib import Path
from unittest.mock import patch

import pytest

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
    r = Rule([y1, y2], [], [], _method, _args, _kwargs, memo)
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

    r = Rule(ys, xs, [], _method, _args, _kwargs, mock_memo)

    m = mocker.patch("jtcmake.rule.rule.save_memo")
    r.update_memo()

    pickle_code = pickle.dumps(["xyz"])
    m.assert_called_once_with(r.metadata_fname, 0)

    # TODO


def test_rule_should_update(tmp_path, mocker):
    """
    Prerequisite: the y-list has at least one item.

    Procedure:
    1. dry_run and any dependency was updated: True
    2. Any x does not exist or has mtime of 0: raise
    3. Any y is missing or has a mtime of 0: True
    4. Any x with IFile type is newer than the oldest y: True
    5. Memoized values are updated: True
    6. Otherwise: False
    """

    q1 = mocker.MagicMock("Rule")
    q2 = mocker.MagicMock("Rule")

    #### multi-y, multi-x, fixed args cases ####

    y1, y2 = File(tmp_path / "f1"), VFile(tmp_path / "f2")
    x1, x2 = File(tmp_path / "x1"), VFile(tmp_path / "x2")

    ys = [y1, y2]
    xs = [x1, x2]

    mock_memo = mocker.MagicMock(IMemo)
    mock_memo.compare.return_value = True
    mock_memo.memo = 0

    r = Rule(ys, xs, [q1, q2], _method, _args, _kwargs, mock_memo)

    # case 1
    touch(x1, x2, y1, y2)
    assert r.should_update(True, True)

    touch(x1, t=0)
    assert r.should_update(True, True)

    # case 2
    for dry_run in (False, True):
        # x1 is missing
        rm(x1)
        touch(x2, y1, y2)
        with pytest.raises(Exception):
            r.should_update(False, dry_run)

        # x1's mtime is 0
        touch(y1, y2, x2)
        touch(x1, t=0)
        with pytest.raises(Exception):
            r.should_update(False, dry_run)

    # case 3
    for dry_run in (False, True):
        # y1 is missing
        rm(y1)
        touch(x1, x2, y2)
        assert r.should_update(False, dry_run)

        # y1 has mtime of 0
        touch(y2)
        touch(y1, t=0)
        assert r.should_update(False, dry_run)

    # case 4
    for dry_run in (False, True):
        touch(x2, t=time.time() - 3)
        touch(y2, t=time.time() - 2)
        touch(x1, t=time.time() - 1)
        touch(y1)
        assert r.should_update(False, dry_run)

    # case 5
    for dry_run in (False, True):
        # no cache case
        touch(y1, y2, x1, x2)
        rm(r.metadata_fname)
        assert r.should_update(False, dry_run)

        # cache differing case
        r.update_memo()
        touch(y1, y2, x1, x2)
        mock_memo.compare.return_value = False
        assert r.should_update(False, dry_run)
        mock_memo.compare.return_value = True

    # case 6
    r.update_memo()
    for dry_run in (False, True):
        # simple
        touch(x1, t=time.time() - 2)
        touch(y1, y2, t=time.time() - 1)
        touch(x2, t=time.time() - 0)
        assert not r.should_update(False, dry_run)

        # equal mtime
        touch(y1, y2, x1, x2)
        assert not r.should_update(False, dry_run)

    # pass case 1 with !dry_run
    touch(x1, x2, y1, y2)
    assert not r.should_update(True, False)

    #### no x ####
    mock_memo = mocker.MagicMock(IMemo)
    mock_memo.compare.return_value = True
    mock_memo.memo = 0

    y1, y2 = File(tmp_path / "f1"), VFile(tmp_path / "f2")
    ys = [y1, y2]
    r = Rule(ys, [], [q1, q2], _method, _args, _kwargs, mock_memo)

    # case 3
    for dry_run in (False, True):
        # y1 is missing
        rm(y1)
        touch(y2)
        assert r.should_update(False, dry_run)

        # y1 is of mtime 0
        touch(y2)
        touch(y1, t=0)
        assert r.should_update(False, dry_run)

    # case 6.
    for dry_run in (False, True):
        touch(y1, y2)
        assert not r.should_update(False, dry_run)


def test_preprocess(tmp_path, mocker):
    """Rule.preprocess(callaback) should make dirs for all its output files."""
    mock_memo = mocker.MagicMock(IMemo)
    y = File(tmp_path / "a")
    r = Rule([y], [], [], _method, _args, _kwargs, mock_memo)
    r.preprocess(lambda *_: None)
    assert os.path.exists(y.path.parent)
    assert os.path.isdir(y.path.parent)


def test_postprocess(tmp_path, mocker):
    """Rule.postprocess(callback, successed:bool) should
    1. if successed,
        1. Create input VFile hash cache
    2. if !successed,
        1. Set mtime of all the existing output files to 0
        2. Delete input VFile hash cache
    """
    mock_save_memo = mocker.patch("jtcmake.rule.rule.save_memo")
    mock_memo = mocker.MagicMock(IMemo)

    y = File(tmp_path / "y")
    x1 = File(tmp_path / "x1")
    x2 = VFile(tmp_path / "x2")

    r = Rule([y], [x1, x2], [], _method, _args, _kwargs, mock_memo)

    touch(x1, x2)
    r.postprocess(lambda *_: None, True)

    mock_save_memo.assert_called_once()

    # TODO: test
