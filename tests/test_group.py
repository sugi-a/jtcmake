import sys, os, shutil, glob, time
from pathlib import Path, PurePath

import pytest

from jtcmake.frontend.group import create_group, SELF
from jtcmake.frontend.file import File, VFile

class _PathLike:
    def __init__(self, p):
        self.p = str(p)

    def __fspath__(self):
        return self.p

fn = lambda *x,**y: None
    

def test_group_add_group():
    #### normal cases ####
    def _test(expect, *args, **kwargs):
        g = create_group('root').add_group(*args, **kwargs)
        assert Path(g._prefix + '_') == Path('root') / (expect + '_')

    # dirname
    _test('x/y/', 'a', 'x/y')
    _test('x/y/', 'x/y')
    _test('x/y/', _PathLike('x/y'))
    _test(os.path.abspath('x/y/') + '/', os.path.abspath('x/y'))

    # prefix
    _test('x/y', 'a', prefix='x/y')
    _test('x/y', 'a', prefix='x/y')
    _test('x/y', 'a', prefix=_PathLike('x/y'))
    _test(os.path.abspath('x/y'), 'a', prefix=os.path.abspath('x/y'))

    # accessing as attribute or via dict key
    g = create_group('root')
    g.add_group('a')
    g.add_group('_a')
    g.add_group('a-')
    assert hasattr(g, 'a')
    assert not hasattr(g, '_a')
    assert not hasattr(g, 'a-')
    assert all((k in g) for k in ('a', '_a', 'a-'))


    #### invalid calls ####
    # prefix only (name needed)
    with pytest.raises(Exception):
        create_group('root').add_group(prefix='a')

    # specify both
    with pytest.raises(Exception):
        create_group('root').add_group('a', dirname='dir', prefix='dir/')

    # specify non-(str|PathLike)
    with pytest.raises(Exception):
        create_group('root').add_group(11)

    with pytest.raises(Exception):
        create_group('root').add_group('a', 11)

    # name being empty str
    with pytest.raises(Exception):
        create_group('root').add_group('', 'a')

    # overwriting registration
    g = create_group('root')
    g.add_group('a')
    with pytest.raises(Exception):
        g.add_group('a')


def test_group_add():
    APath = lambda p: Path(p).absolute()

    ######## Output file path ########
    #### atom path ####
    def _test(expect, *x):
        assert create_group('r').add(*x).path == APath('r') / expect
        assert create_group('r').addvf(*x).path == APath('r') / expect

    # str/PathLike/IFile
    _test('a1', 'a', 'a1', fn)
    _test('a1', 'a', _PathLike('a1'), fn)
    _test('a1', 'a', File('a1'), fn)
    _test('a1', 'a', VFile('a1'), fn)

    # abspath
    _test(os.path.abspath('a1'), 'a', os.path.abspath('a1'), fn)

    # omit path
    _test('a1', 'a1', fn)

    #### structured path ####
    a = create_group('r').add('a', ['a1', {'x': File('a2')}, ('a3',)], fn)
    assert a.path == (APath('r/a1'), {'x': APath('r/a2')}, (APath('r/a3'),))
    a = create_group('r').add('a', ['a1', 'a1'],  fn)
    assert a.path == (APath('r/a1'), APath('r/a1'))

    #### decorator ####
    assert create_group('r').add('a', 'a1', None)(fn).path == APath('r/a1')
    assert create_group('r').add('a1', None)(fn).path == APath('r/a1')

    #### kind of IFile ####
    # add: default is File
    a = create_group('r').add('a', ['a1', VFile('a2')], fn)
    assert isinstance(a[0]._file, File)
    assert isinstance(a[1]._file, VFile)

    # addvf: default is VFile
    a = create_group('r').addvf('a', ['a1', File('a2')], fn)
    assert isinstance(a[0]._file, VFile)
    assert isinstance(a[1]._file, File)

    ######## arguments ########
    #### args and kwargs
    g = create_group('r')
    g.add('a', fn, 1, a=1)
    g.add('b', fn, 1, {'a': [g.a]}, a=1, b=g.a)
    assert g.a._rule.args == (g.a.path, 1) 
    assert g.a._rule.kwargs == {'a': 1} 
    assert g.b._rule.args == (g.b.path, 1, {'a': [g.a.path]} )
    assert g.b._rule.kwargs == {'a': 1, 'b': g.a.path}

    g = create_group('r')
    g.add('a', ['a1', 'a2'], fn)
    g.add('b', ['b1', 'b2'], fn, g.a[0], SELF[0], SELF[1], a=SELF)
    assert g.b._rule.args == (g.a[0].path, g.b[0].path, g.b[1].path)
    assert g.b._rule.kwargs == {'a': list(g.b.path)}

    g = create_group('r')
    g.add('a', fn, VFile('x'))
    assert g.a._rule.args == (g.a.path, APath('x'))

    #### deplist
    g = create_group('r')
    g.add('a', fn)
    g.add('b', fn)
    g.add('c', fn, {'b': g.a, 'a': g.b})
    assert g.c._rule.deplist == [g.b._rule, g.a._rule]


    ######## invalid calls ######## 
    # argument type errors
    with pytest.raises(Exception):
        create_group('r').add(1, fn)

    with pytest.raises(Exception):
        create_group('r').add('a', 1, fn)

    with pytest.raises(Exception):
        create_group('r').add('a', 'a', 1)

    # name being empty str
    with pytest.raises(Exception):
        create_group('root').add('', 'a', fn)

    # overwriting
    g = create_group('r')
    g.add('a', fn)
    with pytest.raises(Exception):
        g.add('a', fn)

    # path collision
    g = create_group('r')
    g.add('a', 'a1', fn)
    with pytest.raises(Exception):
        g.add('b', os.path.abspath('r/a1'), fn)

    # zero paths
    with pytest.raises(Exception):
        create_group('r').add('a', (), fn)

    # inconsistent IFile type
    with pytest.raises(Exception):
        create_group('r').add('a', ['a1', VFile('a1')], fn)

    with pytest.raises(Exception):
        create_group('r').addvf('a', 'a1', fn, File('r/a1'))

    g = create_group('r')
    g.add('a', fn, File('x'))
    with pytest.raises(Exception):
        g.add('b', fn, VFile('x'))

    # output paths not passed to method
    with pytest.raises(Exception):
        create_group('r').add('a', ['a1', 'a2'], fn, SELF[0])
    
    # unsortable dict keys
    with pytest.raises(Exception):
        create_group('r').add('a', fn, {'a': 1, 1: 1})

    # struct_keys for IVFiles not JSON convertible
    with pytest.raises(Exception):
        create_group('r').add('a', fn, {object(): VFile('b')})


def test_rule_touch(tmp_path):
    r = create_group(tmp_path).add('a', ['a1', 'a2'], fn)

    # both
    r.touch()
    assert os.path.getmtime(r[0].path) == os.path.getmtime(r[1].path)

    # a1 only
    r.clean()
    r[0].touch()
    assert os.path.exists(r[0].path)
    assert not os.path.exists(r[1].path)


def test_rule_clean(tmp_path):
    r = create_group(tmp_path).add('a', ['a1', 'a2'], fn)

    # don't raise if file does not exist
    r.clean()

    r.touch()
    r[1].clean()
    assert os.path.exists(r[0].path)
    assert not os.path.exists(r[1].path)


