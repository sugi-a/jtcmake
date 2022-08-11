import sys, os, shutil, glob, time
from pathlib import Path, PurePath

import pytest

from jtcmake import create_group, SELF, MakeSummary


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


@pytest.mark.parametrize("njobs", [None, 1, 2, 3])
def test_1(njobs, tmp_path):
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
    res = g.make(dry_run=True, njobs=njobs)

    assert res == MakeSummary(total=4, update=4, skip=0, fail=0, discard=0)
    assert globfiles(tmp_path) == []

    # run all
    res = g.make(njobs=njobs)

    assert res == MakeSummary(total=4, update=4, skip=0, fail=0, discard=0)

    # make sure to deal with windows path \\
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])
    assert Path(g.aaa.path).read_text() == 'aaa'

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    res = g.g1.ab.make(njobs=njobs)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert globfiles(tmp_path) == \
        sorted(str(Path(x)) for x in ['a.txt', 'g1/ab.txt'])

    # run rest
    mt = os.path.getmtime(g.a.path)
    res = g.make(njobs=njobs)

    assert res == MakeSummary(total=4, update=2, skip=2, fail=0, discard=0)
    assert os.path.getmtime(g.a.path) == mt
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])

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
    res = g.make(keep_going=True)

    assert res == MakeSummary(total=5, update=3, skip=0, fail=1, discard=1)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    g.clean()

    # make (don't stop on fail; multi-thread)
    res = g.make(keep_going=True, njobs=2)

    assert res == MakeSummary(total=5, update=3, skip=0, fail=1, discard=1)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    g.clean()
    assert globfiles(tmp_path) == []


def test_addvf(tmp_path):
    from jtcmake import Atom

    dummy = [1]

    x, y = 'x0', 'y0'
    g = create_group(tmp_path)
    g.addvf('a', lambda p,_: p.write_text(x), Atom(dummy))
    g.add('b', lambda p,_: p.write_text(y), g.a)

    g.make()
    assert (tmp_path / 'b').read_text() == 'y0'

    # when x was modified, y must be updated
    time.sleep(0.01)
    x, y = 'x1', 'y1'
    dummy[0] += 1
    res = g.make()

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert (tmp_path / 'b').read_text() == 'y1'

    # when x was not modified, y must not be updated
    time.sleep(0.01)
    y = 'y2'
    dummy[0] += 1
    res = g.make()

    assert res == MakeSummary(total=2, update=1, skip=1, fail=0, discard=0)
    assert (tmp_path / 'b').read_text() == 'y1'

    # regardless of x, if y's mtime is 0, y must be updated
    os.utime(g.b.path, (0,0))
    dummy[0] += 1
    res = g.make()

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert (tmp_path / 'b').read_text() == 'y2'


def test_memoization(tmp_path):
    from jtcmake.gen_pickle_key import gen_key
    import jtcmake

    def _write(p, t):
        p.write_text(repr(t))

    pickle_key = gen_key()

    #### str case ('abc' -> 'def') ####
    before, after = 'abc', 'def'

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.a.path.read_text() == repr(after)

    #### set case ({1, 2} -> {2, 3}) ####
    before, after = {1,2}, {2,3}

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert g.a.path.read_text() == repr(after)

    #### PurePath/Path case (don't update) (PurePath -> Path) ####
    before, after = PurePath('a'), Path('a')

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, after)
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.a.path.read_text() == repr(before)

    #### ignore change using Atom(_, None) ({1, 2} -> {2, 3}) ####
    before, after = {1,2}, {2,3}

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, jtcmake.Atom(before, lambda _: None))
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, jtcmake.Atom(before, lambda _: None))
    res = g.make()

    assert res == MakeSummary(total=1, update=0, skip=1, fail=0, discard=0)
    assert g.a.path.read_text() == repr(before)  # not after

    
def test_memoization_global_pickle_key(tmp_path):
    import jtcmake

    def _write(p, t):
        p.write_text(repr(t))

    # using the default key
    KEY = b'abc'.hex()
    jtcmake.set_default_pickle_key(KEY)
    
    g = create_group(tmp_path)  # use the default key b'abc'
    g.add('1', _write, "a")
    g.make()

    g = create_group(tmp_path, pickle_key=KEY)  # explicitly give b'abc'
    g.add('1', _write, "b")
    res = g.make()

    # no failure
    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)

    # passing key to create_group
    KEY2 = b'xyz'.hex()
    g = create_group(tmp_path, pickle_key=KEY2)  # use non-default key b'xyz'
    g.add('2', _write, "a")
    g.make()

    g = create_group(tmp_path, pickle_key=KEY2)
    g.add('2', _write, "b")
    res = g.make()

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)

    # failing key validation
    KEY3_1 = b'abc'.hex()
    KEY3_2 = b'xyz'.hex()

    g = create_group(tmp_path, pickle_key=KEY3_1)
    g.add('3', _write, "a")
    g.make()

    g = create_group(tmp_path, pickle_key=KEY3_2)
    g.add('3', _write, "b")
    res = g.make()

    # fail (error on checking update)
    assert res == MakeSummary(total=1, update=0, skip=0, fail=1, discard=0)
