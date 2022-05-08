import sys, os, shutil, glob, time
from pathlib import Path

import pytest

from omochamake import create_group, SELF, nopfx


def nop(*args, **kwargs):
    pass


def test_nopfx(tmp_path):
    tmp_path_str = str(tmp_path)

    dir1 = tmp_path_str + 'dir1/'
    dir2 = tmp_path_str + 'dir2/'

    g = create_group(dir1)
    
    g.add('a1', 'a.txt', nop)
    g.add('a2', nopfx(f'{dir2}a.txt'), nop)
    g.add('a3', nopfx({'a': f'{dir2}a3-1.txt', 0: [f'{dir2}a3-2.txt', f'{dir2}a3-3.txt']}), nop)

    g.add_group('sub1', 'sub/')
    g.add_group('sub2', nopfx(f'{dir2}sub/'))

    g.sub1.add('a', 'a.txt', nop)
    g.sub2.add('a', 'a.txt', nop)


    assert g.a1.path() == f'{dir1}a.txt'
    assert g.a2.path() == f'{dir2}a.txt'
    assert g.a3.path() == {'a': f'{dir2}a3-1.txt', 0: (f'{dir2}a3-2.txt', f'{dir2}a3-3.txt')}
    assert g.sub1.a.path() == f'{dir1}sub/a.txt'
    assert g.sub2.a.path() == f'{dir2}sub/a.txt'

