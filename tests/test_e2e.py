import sys, os, shutil, glob, time
from pathlib import Path, PurePath

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
    g.make(dry_run=True, nthreads=nthreads)
    assert globfiles(tmp_path) == []


    # run all
    g.make(nthreads=nthreads)
    # make sure to deal with windows path \\
    assert globfiles(tmp_path) == sorted(
        str(Path(x)) for x in ['a.txt', 'aa.txt', 'aaa.txt', 'g1/ab.txt'])
    assert Path(g.aaa.path).read_text() == 'aaa'

    # clean all
    g.clean()
    assert globfiles(tmp_path) == []

    # run some
    g.g1.ab.make(nthreads=nthreads)
    assert globfiles(tmp_path) == \
        sorted(str(Path(x)) for x in ['a.txt', 'g1/ab.txt'])

    # run rest
    mt = os.path.getmtime(g.a.path)
    g.make(nthreads=nthreads)
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
    g.make(keep_going=True)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    # make (don't stop on fail; multi-thread)
    g.make(keep_going=True, nthreads=2)
    assert globfiles(tmp_path) == sorted(['a.txt', 'b2.txt', 'c2.txt'])

    g.clean()
    assert globfiles(tmp_path) == []


def test_force_update(tmp_path):
    x = '1'
    def _writer(p):
        p.write_text(x)

    # no-force-update case
    r = create_group(tmp_path).add('a', _writer)
    r.make()
    x = '2'
    r.make()
    assert (tmp_path / 'a').read_text() == '1'
    create_group(tmp_path).add('a', _writer).make()
    assert (tmp_path / 'a').read_text() == '1'

    # force-update case
    r = create_group(tmp_path).add('a', _writer, force_update=True)
    r.make()
    assert (tmp_path / 'a').read_text() == '2'
    x = '3'
    r.make()
    assert (tmp_path / 'a').read_text() == '3'

    # VFile
    x = '4'
    r = create_group(tmp_path).addvf('a', _writer, force_update=True).make()
    assert (tmp_path / 'a').read_text() == '4'


def test_addvf(tmp_path):
    x, y = 'x0', 'y0'
    g = create_group(tmp_path)
    g.addvf('a', lambda p: p.write_text(x), force_update=True)
    g.add('b', lambda p,_: p.write_text(y), g.a)

    g.make()
    assert (tmp_path / 'b').read_text() == 'y0'

    time.sleep(0.01)
    x, y = 'x1', 'y1'
    g.make()
    assert (tmp_path / 'b').read_text() == 'y1'

    time.sleep(0.01)
    y = 'y2'
    g.make()
    assert (tmp_path / 'b').read_text() == 'y1'

    os.utime(g.b.path, (0,0))
    g.make()
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
    g.make()

    assert g.a.path.read_text() == repr(after)

    #### set case ({1, 2} -> {2, 3}) ####
    before, after = {1,2}, {2,3}

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, after)
    g.make()

    assert g.a.path.read_text() == repr(after)

    #### PurePath/Path case (PurePath -> Path) ####
    before, after = PurePath('a'), Path('a')

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, before)
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, after)
    g.make()

    assert g.a.path.read_text() == repr(before)

    #### ignore change ({1, 2} -> {2, 3}) ####
    before, after = {1,2}, {2,3}

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, jtcmake.Atom(before, lambda _: None))
    g.make()

    assert g.a.path.read_text() == repr(before)

    g = create_group(tmp_path, pickle_key=pickle_key)
    g.add('a', _write, jtcmake.Atom(before, lambda _: None))
    g.make()

    assert g.a.path.read_text() == repr(before)  # not after

    
