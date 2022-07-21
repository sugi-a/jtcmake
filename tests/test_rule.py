import sys, os, shutil, glob, time
from pathlib import Path
from unittest.mock import patch

import pytest

from jtcmake.frontend.rule import \
    Rule, save_vfile_hashes, load_vfile_hashes, create_vfile_hashes

from jtcmake.frontend.file import File, VFile, IFile


_args = (object(),)
_kwargs = {'a': object()}
_method = lambda: None

def rm(*paths):
    for p in paths:
        if isinstance(p, IFile):
            p = p.path
        try:
            os.remove(p)
        except:
            pass

def touch(*paths, t=None):
    if t is None:
        t = time.time()

    for p in paths:
        if isinstance(p, IFile):
            p = p.path
        Path(p).touch()
        os.utime(p, (t,t))


def test_metadata_fname():
    """Rule.metadata_fname is decided based on the name of the first
    output file (p) as follows:
        metadata_fname := p.parent / '.jtcmake' / p.name
    """
    y1, y2 = File(Path('a/b.c')), File(Path('d/e.f'))
    r = Rule([y1, y2], [], [], _method, _args, _kwargs)
    assert str(r.metadata_fname) == 'a/.jtcmake/b.c'


def test_create_vfile_hashes(mocker):
    """create_vfile_hashes(vfile_list)
    creates a list where each element corresponds to
    a VFile and is a triple (key, hash code, mtime).
    `key` is the StructKey for the VFile, hash code is the hash of the VFile,
    and mtime is the time at which the hash was computed.
    """
    f1, f2 = (mocker.MagicMock(VFile) for _ in range(2))
    f1.get_hash = mocker.MagicMock(return_value='a')
    f2.get_hash = mocker.MagicMock(return_value='b')

    mocker.patch(
        'jtcmake.frontend.file.os.path.getmtime',
        side_effect=lambda p: 1 if p == f1.path else 2
    )

    res = create_vfile_hashes([('k1', f1), ('k2', f2)])
    assert res == [['k1', 'a', 1], ['k2', 'b', 2]]


def test_update_xvfile_hashes(tmp_path, mocker):
    y1, y2 = File(tmp_path / 'f1'), VFile(tmp_path / 'f2')
    x1, x2 = (File(tmp_path / f'x{i}') for i in (1,2))
    k1, k2 = ('k1',), ('k2',)
    ys = [y1, y2]
    xs = [(k1,y1), (k2,y2)]

    r = Rule(ys, xs, [], _method, _args, _kwargs)

    m = mocker.patch('jtcmake.frontend.rule.save_vfile_hashes')
    r.update_xvfile_hashes()

    m.assert_called_once_with(r.metadata_fname, [(k2,y2)])
    

def test_rule_should_update(tmp_path, mocker):
    """
    Assumption: the y-list has at least one item.

    Procedure:
    1. dry_run and any dependency was updated: True
    2. Any x does not exist or has mtime of 0:
        1. dry_run: True
        2. !dry_run: raise
    3. Any y is missing: True
    4. Any y has a mtime of 0: True
    5. No x: False
    6. Let Y := the oldest y,
        1. Any x with non-IVFile type is newer than Y: True
        2. Any x with IVFile type, whose location in the argument structure
           is specified with keys K=(k_1, ..., k_n), is newer than Y and
           the cached VFile hash for K is not equal to hash(x): True
    7. Otherwise: False
    """

    q1 = mocker.MagicMock('Rule')
    q2 = mocker.MagicMock('Rule')

    #### multi-y, multi-x cases ####
    y1, y2 = File(tmp_path / 'f1'), VFile(tmp_path / 'f2')
    x1, x2 = File(tmp_path / 'x1'), VFile(tmp_path / 'x2')
    k1, k2 = ('k1',), ('k2',)

    ys = [y1, y2]
    xs = [(k1,x1), (k2,x2)]

    r = Rule(ys, xs, [q1, q2], _method, _args, _kwargs)

    # case 1
    touch(x1, x2, y1, y2)
    assert r.should_update({q1}, True)

    # case 2.1: x1 is missing
    rm(x1); touch(x2, y1, y2)
    assert r.should_update(set(), True)

    # case 2.1: x1's mtime is 0
    touch(y1, y2, x2); touch(x1, t=0)
    assert r.should_update(set(), True)

    # case 2.2: x1 is missing
    rm(x1); touch(x2, y1, y2)
    with pytest.raises(Exception):
        r.should_update(set(), False)

    # case 2.2: x1's mtime is 0
    touch(y1, y2, x2); touch(x1, t=0)
    with pytest.raises(Exception):
        r.should_update(set(), False)

    # case 3: y1 is missing
    rm(y1); touch(x1, x2, y2)
    assert r.should_update(set(), False)

    # case 6.1
    touch(y2, x1, x2); touch(y1, t=time.time() - 1)
    assert r.should_update(set(), False)

    # case 6.2
    touch(y1, y2, x1, t=time.time() - 1) 
    touch(x2)

    rm(r.metadata_fname) # no cache
    assert r.should_update(set(), False)

    r.update_xvfile_hashes()
    x2.path.write_text('a') # hash differs
    assert r.should_update(set(), False)

    # case 7
    # simple
    touch(y1, y2); touch(x1, x2, t=time.time()-1)
    assert not r.should_update(set(), False)

    # equal mtime
    touch(y1, y2, x1, x2)
    assert not r.should_update(set(), False)

    # check VFile hash
    touch(y1, y2, x1, x2, t=time.time() - 1)
    r.update_xvfile_hashes()
    touch(x2); 
    assert not r.should_update(set(), False)

    # pass case 1 with !dry_run
    touch(x1, x2, y1, y2)
    assert not r.should_update({q1}, False)


    #### no x case ####
    y1, y2 = File(tmp_path / 'f1'), VFile(tmp_path / 'f2')
    ys = [y1, y2]
    r = Rule(ys, [], [q1, q2], _method, _args, _kwargs)

    # case 3: y1 is missing
    rm(y1); touch(y2)
    assert r.should_update(set(), False)

    # case 4: y1 is of mtime 0
    touch(y2); touch(y1, t=0)
    assert r.should_update(set(), False)

    # case 5
    touch(y1, y2)
    assert not r.should_update(set(), False)


def test_preprocess(tmp_path):
    """Rule.preprocess(callaback) should make dirs for all its output files.
    """
    y = File(tmp_path / 'a')
    r = Rule([y], [], [], _method, _args, _kwargs)
    r.preprocess(lambda *_: None)
    assert os.path.exists(y.path.parent)
    assert os.path.isdir(y.path.parent)


def test_postprocess(tmp_path):
    """Rule.postprocess(callback, successed:bool) should
    1. if successed,
        1. Create input VFile hash cache
    2. if !successed,
        1. Set mtime of all the existing output files to 0
        2. Delete input VFile hash cache
    """
    y = File(tmp_path / 'y')
    x1 = File(tmp_path / 'x1')
    x2 = VFile(tmp_path / 'x2')

    r = Rule([y], [('k1', x1), ('k2', x2)], [], _method, _args, _kwargs)

    touch(x1, x2)
    r.postprocess(lambda *_: None, True)

    saved = load_vfile_hashes(r.metadata_fname)
    assert saved == create_vfile_hashes([('k2', x2)])
