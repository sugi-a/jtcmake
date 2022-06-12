import sys, os, shutil, glob, time
from pathlib import Path

import pytest

from omochamake.core.decls import RuleMemo, MemoSourceFile, Rule


def test_RuleMemo(tmp_path):
    fn = lambda x:None

    mem = tmp_path / 'mem1'

    r = RuleMemo(
        'name', fn, [], {},
        set(), set(), set(), ([], {}), mem
    )

    assert r.should_update()

    r.update_memo()
    assert os.path.exists(mem)

    assert not r.should_update()

    r = RuleMemo(
        'name', fn, [], {},
        set(), set(), set(), ([], {}), mem
    )

    assert not r.should_update()

    r = RuleMemo(
        'name', fn, [], {},
        set(), set(), set(), ([1], {}), mem
    )

    assert r.should_update()
    r.update_memo()
    assert not r.should_update()

            
    mem = tmp_path / 'mem2'

    r = RuleMemo(
        'name', fn, [], {}, set(),
        {tmp_path / 'out.txt'}, set(),
        ([1, MemoSourceFile(tmp_path / 'in.txt')], {}), mem
    )

    assert r.should_update()
    (tmp_path / 'out.txt').touch()
    assert r.should_update()
    r.update_memo()
    assert not r.should_update()
    (tmp_path / 'in.txt').write_text('a')
    assert r.should_update()
    r.update_memo()
    assert not r.should_update()
    (tmp_path / 'in.txt').write_text('a')
    assert not r.should_update()
    (tmp_path / 'in.txt').write_text('b')
    assert r.should_update()


