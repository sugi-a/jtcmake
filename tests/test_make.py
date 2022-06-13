import sys, os, shutil
from pathlib import Path
import pytest

from omochamake.core import make, Events, Rule, NOP


def touch(*fns):
    for fn in fns:
        Path(fn).touch()


def write(fn, text):
    Path(fn).write_text(text)


def remove(*fns):
    for fn in fns:
        Path(fn).unlink()


def fail(*args, exc=None, **kwargs):
    if exc is None:
        exc = Exception()
    raise exc


def cmp_event(e1, e2):
    return e1.__class__ == e2.__class__ and e1.rule() == e2.rule()


def cmp_events(events1, events2):
    return len(events1) == len(events2) \
        and all(cmp_event(e1, e2) for e1,e2 in zip(events1, events2))


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

    a1 = tmp_path / 'a1'
    r1 = Rule('name', touch, [a1], {}, set(), {a1}, set())
    a2 = tmp_path / 'a2'
    r2 = Rule('name', touch, [a2], {}, {r1}, {a2}, {a1})

    # dry-run r1
    events.clear()
    make([r1], True, False, callback)
    assert cmp_events(events, [Events.DryRun(r1)])

    # dry-run r2
    events.clear()
    make([r2], True, False, callback)
    assert cmp_events(events, [Events.DryRun(r1), Events.DryRun(r2)])

    # dry-run after real-run
    make([r1], False, False, callback)
    events.clear()
    make([r2], True, False, callback)
    assert cmp_events(events, [Events.Skip(r1), Events.DryRun(r2)])

    # r2 is present but r1 is not
    make([r2], False, False, callback)
    remove(a1)
    events.clear()
    make([r2], True, False, callback)
    assert cmp_events(events, [Events.DryRun(r1), Events.DryRun(r2)])


def test_skip_readonly(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a1'
    r1 = Rule('name', NOP, [], {}, set(), {}, set())
    a1.touch()

    a2 = tmp_path / 'a2'
    r2 = Rule('name', touch, [a2], {}, {r1}, {a2}, {a1})

    # Dry-run
    events.clear()
    make([r2], True, False, callback)
    assert len(events) == 2
    assert isinstance(events[0], Events.SkipReadonly)
    assert isinstance(events[1], Events.DryRun)
    assert events[0].rule() == r1
    assert events[1].rule() == r2

    # run
    events.clear()
    make([r2], False, False, callback)
    assert len(events) == 3
    assert isinstance(events[0], Events.SkipReadonly)
    assert isinstance(events[1], Events.Start)
    assert isinstance(events[2], Events.Done)
    assert events[0].rule() == r1
    assert events[1].rule() == r2
    assert events[2].rule() == r2


def test_mkdir_error(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'd/a1'
    r1 = Rule('name', touch, [a1], {}, set(), {a1}, set())
    touch(tmp_path / 'd')

    events.clear()
    make([r1], False, False, callback)
    assert cmp_events(
        events, [
            Events.MkdirError(r1, None),
            Events.Start(r1),
            Events.ExecError(r1, None),
        ]
    )


def test_exec_error(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a'
    r1 = Rule('name', fail, [a1], {}, set(), {a1}, set())

    events.clear()
    make([r1], False, False, callback)
    assert cmp_events(
        events, [
            Events.Start(r1),
            Events.ExecError(r1, None),
        ]
    )


def test_stop_on_fail(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a1'
    r1 = Rule('name', fail, [a1], {}, set(), {a1}, set())
    a2 = tmp_path / 'a2'
    r2 = Rule('name', touch, [a2], {}, {r1}, {a2}, set())

    events.clear()
    make([r2], False, True, callback)
    assert cmp_events(
        events, [
            Events.Start(r1),
            Events.ExecError(r1, None),
            Events.StopOnFail(None),
        ]
    )


def test_post_proc_error(tmp_path):
    events = []
    def callback(event):
        events.append(event)

    a1 = tmp_path / 'a1'
    r1 = Rule('name', lambda x:None, [a1], {}, set(), {a1}, set())

    events.clear()
    make([r1], False, False, callback)
    assert cmp_events(
        events, [
            Events.Start(r1),
            Events.PostProcError(r1, None),
        ]
    )


    
