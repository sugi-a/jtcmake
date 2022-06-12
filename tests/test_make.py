import sys, os
from pathlib import Path
import pytest

from omochamake.core import make, Events, Rule


def touch(*fns):
    for fn in fns:
        Path(fn).touch()

def write(fn, text):
    Path(fn).write_text(text)

def remove(*fns):
    for fn in fns:
        Path(fn).unlink()


def test_basic(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a1'
    r1 = Rule('name', touch, [str(a1)], {}, set(), {str(a1)}, set())

    a2 = tmp_path / 'a2'
    r2 = Rule('name', touch, [str(a2)], {}, {r1}, {str(a2)}, {str(a1)})

    # pass both
    events.clear()
    make([r1, r2], False, False, callback)
    assert len(events) == 4
    assert isinstance(events[0], Events.Start)
    assert isinstance(events[1], Events.Done)
    assert isinstance(events[2], Events.Start)
    assert isinstance(events[3], Events.Done)
    assert events[0].rule() == r1
    assert events[1].rule() == r1
    assert events[2].rule() == r2
    assert events[3].rule() == r2

    # pass r1
    events.clear()
    remove(a1, a2)
    make([r1], False, False, callback)

    assert len(events) == 2
    assert isinstance(events[0], Events.Start)
    assert isinstance(events[1], Events.Done)
    assert events[0].rule() == r1
    assert events[1].rule() == r1

    # pass r2
    events.clear()
    remove(a1)
    make([r2], False, False, callback)

    assert len(events) == 4
    assert isinstance(events[0], Events.Start)
    assert isinstance(events[1], Events.Done)
    assert isinstance(events[2], Events.Start)
    assert isinstance(events[3], Events.Done)
    assert events[0].rule() == r1
    assert events[1].rule() == r1
    assert events[2].rule() == r2
    assert events[3].rule() == r2


def test_skip(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a1'
    r1 = Rule('name', touch, [str(a1)], {}, set(), {str(a1)}, set())

    a2 = tmp_path / 'a2'
    r2 = Rule('name', touch, [str(a2)], {}, {r1}, {str(a2)}, {str(a1)})

    # skip both
    make([r2], False, False, callback)
    events.clear()
    make([r2], False, False, callback)
    assert len(events) == 2
    assert isinstance(events[0], Events.Skip)
    assert isinstance(events[1], Events.Skip)
    assert events[0].rule() == r1
    assert events[1].rule() == r2

    # skip r1
    remove(a1, a2)
    make([r1], False, False, callback)
    events.clear()
    make([r2], False, False, callback)
    assert len(events) == 3
    assert isinstance(events[0], Events.Skip)
    assert isinstance(events[1], Events.Start)
    assert isinstance(events[2], Events.Done)
    assert events[0].rule() == r1
    assert events[1].rule() == r2
    assert events[2].rule() == r2


def test_dryrun(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a = tmp_path / 'a'
    r1 = Rule('name', touch, [str(a)], {}, set(), {str(a)}, set())

    # dry-run
    events.clear()
    make([r1], True, False, callback)

    assert len(events) == 1
    assert isinstance(events[0], Events.DryRun)

    # dry-run after real-run
    make([r1], False, False, callback)
    events.clear()
    make([r1], True, False, callback)
    assert len(events) == 1
    assert isinstance(events[0], Events.Skip)


def test_skip_readonly(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a = tmp_path / 'a'
    r1 = Rule('name', touch, [str(a)], {}, set(), {str(a)}, set())

