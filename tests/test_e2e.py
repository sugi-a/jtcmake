import sys, os, shutil, glob, time
from pathlib import Path

import pytest

from omochamake import create_group, SELF, nopfx


def touch(*dst):
    for p in dst:
        Path(p).touch()


def add_text(dst, src, text=None, t=0):
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
    g.make(dry_run=True, nthreads=nthreads)
    assert globfiles(tmp_path) == []


    # run all
    g.make(nthreads=nthreads)
    assert globfiles(tmp_path) == sorted(['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])
    assert Path(g.aaa.path()).read_text() == 'aaa'

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    g.g1.ab.make(nthreads=nthreads)
    assert globfiles(tmp_path) == sorted(['a.txt', 'g1/ab.txt'])

    # run rest
    mt = os.path.getmtime(g.a.path())
    g.make(nthreads=nthreads)
    assert os.path.getmtime(g.a.path()) == mt
    assert os.path.getmtime(g.aaa.path()) > mt
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


def test_3(tmp_path):
    # safety guards on rule creation

    g = create_group(tmp_path)

    g.add('a', 'a.txt', add_text, None, 'a')

    # dupe key
    with pytest.raises(KeyError) as e:
        g.add('a', 'b.txt', add_text, g.a, 'a')

    g.add('b', 'b.txt', add_text, g.a, 'a')

    # dupe path
    with pytest.raises(ValueError) as e:
        g.add('c', 'b.txt', add_text, g.b, 'a')

    g.add('c', 'c.txt', add_text, g.b, 'a')

    # dupe key (sub-group vs rule)
    with pytest.raises(KeyError) as e:
        g.add_group('c', 'sub/')

    g.add_group('sub', 'sub/')

    # dupe path (complex)
    with pytest.raises(ValueError) as e:
        g.sub.add('a', '../a.txt', add_text, g.c)

    g.sub.add('a', '../sub-a.txt', add_text, g.c)

    # foreign rule
    g2 = create_group(tmp_path / 'tmp')
    with pytest.raises(ValueError) as e:
        g2.add('a', 'a.txt', add_text, g.b, 'a')

    g2.add('a', 'a.txt', add_text, None, 'a')

    # empty path
    with pytest.raises(ValueError) as e:
        g2.add('b', (), add_text, g2.a, 'a')

    # illegal path
    with pytest.raises(TypeError) as e:
        g2.add('b', ['b.txt', 1], cp_1_to_n, g2.a)

    # unused paths
    with pytest.raises(ValueError) as e:
        g2.add('b', ['b1.txt', 'b2.txt', 'b3.txt'], cp_1_to_n, [SELF[0], SELF[1]], g2.a)


def test_4(tmp_path):
    # make failure
    g = create_group(tmp_path)
    
    g.add('a', 'a.txt', touch)
    g.add('b1', 'b1.txt', fail, g.a)
    g.add('b2', 'b2.txt', add_text, g.a, t=1)
    g.add('c1', 'c1.txt', add_text, g.b1)
    g.add('c2', 'c2.txt', add_text, g.b2)

    # make (don't stop on fail)
    g.make(stop_on_fail=False)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    # make (don't stop on fail; multi-thread)
    g.make(stop_on_fail=False, nthreads=2)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    g.clean()
    assert globfiles(tmp_path) == []


def test_5(tmp_path):
    # readonly feature
    (tmp_path / 'a.txt').touch()
    (tmp_path / 'b.txt').touch()

    g = create_group(tmp_path)
    
    g.add_readonly('a', 'a.txt')
    g.add('b', 'b.txt', touch)

    g.clean()
    assert globfiles(tmp_path) == ['a.txt']


def test_mem(tmp_path):
    # test memoization rules
    ran = False
    def method(dst, *args):
        nonlocal ran
        ran = True
        touch(dst)

    (tmp_path / 'a.txt').write_text('abc')

    g = create_group(tmp_path)
    g.add_readonly('a', 'a.txt')
    g.add_memo('b', 'b.txt', 'b.memmem', method, g.a, 1)

    # first run (executed)
    ran = False
    g.make()
    assert ran
    assert os.path.exists(tmp_path / 'b.memmem')

    # 2nd run with touched src (skipped)
    (tmp_path / 'a.txt').touch()
    ran = False
    g.make()
    assert not ran

    # re-create the rule and run (skipped)
    g = create_group(tmp_path)
    g.add_readonly('a', 'a.txt')
    g.add_memo('b', 'b.txt', 'b.memmem', method, g.a, 1)
    ran = False
    g.make()
    assert not ran

    # re-create the rule with different input and run (executed)
    g = create_group(tmp_path)
    g.add_readonly('a', 'a.txt')
    g.add_memo('b', 'b.txt', 'b.memmem', method, g.a, 2)
    ran = False
    g.make()
    assert ran

    # 2nd run with modified src (executed)
    (tmp_path / 'a.txt').write_text('xyz')
    ran = False
    g.make()
    assert ran

    # 3rd run (skipped)
    ran = False
    g.make()
    assert not ran

