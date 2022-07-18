import sys, os, shutil, glob, time
from pathlib import Path

import pytest

from jtcmake import create_group, SELF


def touch(*dst):
    for p in dst:
        Path(p).touch()


def add_text(dst, src, text=None, t=0):
    print('add text', dst, src, text)
    src = '' if src is None else Path(src).read_text()
    text = '' if text is None else text

    if t > 0:
        time.sleep(t)

    Path(dst).write_text(src + text)


def cp_1_to_n(dsts, src):
    for d in dsts:
        shutil.copy(src, d)


def cp_n_to_1(dst, srcs):
    Path(dst).write_text(''.join(Path(s).read_text() for s in srcs))


def fail(*args, **kwargs):
    raise Exception('FAIL')


def globfiles(dirname):
    ps = glob.iglob(f'{dirname}/**', recursive=True)
    ps = [os.path.relpath(p, dirname) for p in ps if os.path.isfile(p)]
    ps.sort()
    return ps


@pytest.mark.parametrize("nthreads", [0, 1, 2])
def test_1(nthreads, tmp_path):
    """basics"""

    g = create_group(tmp_path)

    g.add('a', 'a.txt', add_text, None, 'a')
    g.add('aa', 'aa.txt', add_text, SELF, g.a, 'a')

    @g.add('aaa', 'aaa.txt', None, g.aa)
    def _(dst, src):
        add_text(dst, src, 'a')

    g1 = g.add_group('g1', 'g1/')
    g1.add('ab', 'ab.txt', add_text, g.a, 'b')


    # dry-run
    #g.make(dry_run=True, nthreads=nthreads)
    g.make(dry_run=True)
    assert globfiles(tmp_path) == []


    # run all
    #g.make(nthreads=nthreads)
    g.make()
    assert globfiles(tmp_path) == sorted(['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])
    assert Path(g.aaa.path).read_text() == 'aaa'

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    #g.g1.ab.make(nthreads=nthreads)
    g.g1.ab.make()
    assert globfiles(tmp_path) == sorted(['a.txt', 'g1/ab.txt'])

    # run rest
    mt = os.path.getmtime(g.a.path)
    #g.make(nthreads=nthreads)
    g.make()
    assert os.path.getmtime(g.a.path) == mt
    assert os.path.getmtime(g.aaa.path) > mt
    assert globfiles(tmp_path) == sorted(['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])

    # clean some
    g.a.clean()
    g.g1.clean()
    assert globfiles(tmp_path) == sorted(['aa.txt', 'aaa.txt'])


def test_2(tmp_path):
    # nested path and args
    g = create_group(tmp_path)

    g.add('a', 'a.txt', add_text, None, 'a')
    g.add('b', ('b1.txt', {'x': 'b2.txt'}), cp_1_to_n, [SELF[0], SELF[1].x], g.a)
    g.add('c', 'c.txt', add_text, g.b[0], 'a')

    # run
    g.make()
    assert globfiles(tmp_path) == sorted(['a.txt', 'b1.txt', 'b2.txt', 'c.txt'])


def test_4(tmp_path):
    # make failure
    g = create_group(tmp_path)
    
    g.add('a', 'a.txt', touch)
    g.add('b1', 'b1.txt', fail, g.a)
    g.add('b2', 'b2.txt', add_text, g.a, t=1)
    g.add('c1', 'c1.txt', add_text, g.b1)
    g.add('c2', 'c2.txt', add_text, g.b2)

    # make (don't stop on fail)
    g.make(keep_going=True)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    ## make (don't stop on fail; multi-thread)
    #g.make(stop_on_fail=False, nthreads=2)
    #assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    g.clean()
    assert globfiles(tmp_path) == []


