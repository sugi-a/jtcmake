import sys, os, shutil, glob, time
from pathlib import Path

import pytest

from omochamake import create_group, SELF, nopfx


def nop(*args, **kwargs):
    pass


def test_group_nopfxpath(tmp_path):
    tmp_path_str = str(tmp_path)

    dir1 = tmp_path / 'dir1'
    dir2 = tmp_path / 'dir2'

    g = create_group(dir1)
    
    g.add('a1', 'a.txt', nop)
    g.add('a2', nopfx(f'{dir2}/a.txt'), nop)
    g.add('a3', nopfx({'a': f'{dir2}/a3-1.txt', 0: [f'{dir2}/a3-2.txt', f'{dir2}/a3-3.txt']}), nop)

    g.add_group('sub1', 'sub/')
    g.add_group('sub2', nopfx(f'{dir2}/sub/'))

    g.sub1.add('a', 'a.txt', nop)
    g.sub2.add('a', 'a.txt', nop)


    assert g.a1.path() == f'{dir1}/a.txt'
    assert g.a2.path() == f'{dir2}/a.txt'
    assert g.a3.path() == {'a': f'{dir2}/a3-1.txt', 0: (f'{dir2}/a3-2.txt', f'{dir2}/a3-3.txt')}
    assert g.sub1.a.path() == f'{dir1}/sub/a.txt'
    assert g.sub2.a.path() == f'{dir2}/sub/a.txt'


def test_group_path():
    fn = lambda x: None
    p = Path('path')

    # Rule and readonly Rule
    g = create_group(p)
    g.add('a', 'a.txt', fn)
    g.add('b', ['b1', 'b2'], fn)
    g.add('c.txt', fn)
    g.add_readonly('r', 'r')

    assert g.a.path() == str(p / 'a.txt')
    assert g.b.path() == (str(p / 'b1'), str(p / 'b2'))
    assert g['c.txt'].path() == str(p / 'c.txt')
    assert g.r.path() == str(p / 'r')

    # memoization Rule
    g = create_group(p)
    g.add_memo('a', 'a.txt', 'a.m', fn)
    g.add_memo('b', 'b.txt', fn)
    g.add_memo('c', fn, 1)

    assert g.a.path() == str(p / 'a.txt')
    assert g.a._rule.memo_save_path == str(p / 'a.m')
    assert g.b.path() == str(p / 'b.txt')
    assert g.b._rule.memo_save_path == str(p / 'b.memo')
    assert g.c.path() == str(p / 'c')
    assert g.c._rule.memo_save_path == str(p / 'c.memo')

    # sub group
    g = create_group(p)
    g.add_group('sub')
    g.sub.add('a', fn)
    g['sub'].add_group('sub2').add('a', fn)
    g.add_group('sub2', 'subdir').add('a', fn)

    assert g.sub.a.path() == str(p / 'sub/a')
    assert g.sub.sub2.a.path() == str(p / 'sub/sub2/a')
    assert g.sub2.a.path() == str(p / 'subdir/a')

    # path prefix
    g = create_group(path_prefix='pfx-')
    g.add('a', fn)
    g.add_group('sub').add('a', fn)
    g.add_group('sub2', path_prefix='sub-').add('a', fn)

    assert g.a.path() == 'pfx-a'
    assert g.sub.a.path() == 'pfx-sub/a'
    assert g.sub2.a.path() == 'pfx-sub-a'

    # nested path
    g = create_group('p')
    g.add('a', ['a', {'b': 'b'}], fn)

    assert g.a.path() == ('p/a', {'b': 'p/b'})


def test_decorator_style_add():
    fn = lambda: None
    g = create_group(Path('p'))
    g.add('a', 'a.txt', None)(fn)
    g.add('b', None)(fn)
    g.add_memo('c', 'c.txt', 'c.m', None)(fn)
    g.add_memo('d', 'd.txt', None)(fn)
    g.add_memo('e', None)(fn)

    assert g.a.path() == 'p/a.txt'
    assert g.b.path() == 'p/b'
    assert g.c.path() == 'p/c.txt'
    assert g.d.path() == 'p/d.txt'
    assert g.e.path() == 'p/e'
    assert g.a._rule.method == fn
    assert g.b._rule.method == fn
    assert g.c._rule.method == fn
    assert g.d._rule.method == fn
    assert g.e._rule.method == fn


def test_method_args():
    fn = lambda: None
    g = create_group('p')
    g.add('a', 'a.txt', fn)
    g.add('b', 'b', fn, 1, x=2)
    g.add('c', ['c1', {'c2': 'c2'}], fn)
    g.add('d', fn, g.c[0], g.c[1])
    g.add('e', fn, 1, SELF, x=SELF)
    g.add('f', ['f1', 'f2'], fn, {'a': SELF[1]}, SELF)

    assert g.a._rule.args == ('p/a.txt',)
    assert g.a._rule.kwargs == {}
    assert g.b._rule.args == ('p/b', 1)
    assert g.b._rule.kwargs == {'x': 2}
    assert g.c._rule.args == (['p/c1', {'c2': 'p/c2'}],)
    assert g.d._rule.args == ('p/d', 'p/c1', {'c2': 'p/c2'})
    assert g.e._rule.args == (1, 'p/e')
    assert g.e._rule.kwargs == {'x': 'p/e'}
    assert g.f._rule.args == ({'a': 'p/f2'}, ['p/f1', 'p/f2'],)


