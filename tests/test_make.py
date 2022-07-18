import sys, os, shutil
import pytest

from jtcmake.core.rule import Event, IRule
from jtcmake.core.make import make
from jtcmake.core import events

def fail(*args, exc=None, **kwargs):
    if exc is None:
        exc = Exception()
    raise exc


def assert_same_event(e1, e2):
    assert type(e1) == type(e2)
    assert e1.__dict__ == e2.__dict__


def assert_same_log_item(x1, x2):
    if isinstance(x1, Event):
        assert_same_event(x1, x2)
    else:
        assert len(x1) == len(x2)
        for u,v in zip(x1, x2):
            if isinstance(u, Event):
                assert_same_event(u, v)
            else:
                assert u == v


def assert_same_log(log1, log2):
    for x1, x2 in zip(log1, log2):
        assert_same_log_item(x1, x2)

log = []

def callback(event):
    log.append(event)

class MockRule(IRule):
    def __init__(
        self, deplist, args, kwargs, method,
        should_update=True, preprocess_err=None, postprocess_err=None
    ):
        self._deplist = deplist
        self._should_update = should_update
        self._args = args
        self._kwargs = kwargs
        self._method = method
        self._preprocess_err = preprocess_err
        self._postprocess_err = postprocess_err

    def should_update(self, updated_rules, dry_run):
        log.append(('should_update', self, set(updated_rules), dry_run))
        if isinstance(self._should_update, Exception):
            raise self._should_update
        return self._should_update

    def preprocess(self, callback):
        log.append(('preprocess', self))
        if self._preprocess_err is not None:
            raise self._preprocess_err

    def postprocess(self, callback, succ):
        log.append(('postprocess', self, succ))
        if self._postprocess_err is not None:
            raise self._postprocess_err

    @property
    def method(self): return self._method

    @property
    def args(self): return self._args

    @property
    def kwargs(self): return self._kwargs

    @property
    def deplist(self): return self._deplist


def test_basic():
    args, kwargs = (object(),), {'a': object()}

    def method(*args_, **kwargs_):
        assert args_ == args
        assert kwargs_ == kwargs
        log.append(('method', ))

    r1 = MockRule([], args, kwargs, method)
    r2 = MockRule([r1], args, kwargs, method)

    # pass both
    log.clear()
    make([r1, r2], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        ('method',),
        ('postprocess', r1, True),
        events.Done(r1),

        ('should_update', r2, {r1}, False),
        events.Start(r2),
        ('preprocess', r2),
        ('method',),
        ('postprocess', r2, True),
        events.Done(r2),
    ])

    # pass r1
    log.clear()
    make([r1], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        ('method',),
        ('postprocess', r1, True),
        events.Done(r1)
    ])

    # pass r2
    log.clear()
    make([r2], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        ('method',),
        ('postprocess', r1, True),
        events.Done(r1),

        ('should_update', r2, {r1}, False),
        events.Start(r2),
        ('preprocess', r2),
        ('method',),
        ('postprocess', r2, True),
        events.Done(r2),
    ])


def test_skip():
    args, kwargs = (object(),), {'a': object()}

    def method(*args_, **kwargs_):
        assert args_ == args
        assert kwargs_ == kwargs
        log.append(('method', ))

    r1 = MockRule([], args, kwargs, method)
    r2 = MockRule([r1], args, kwargs, method)

    # skip both
    log.clear()
    r1._should_update = False
    r2._should_update = False

    make([r2], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Skip(r1),
        ('should_update', r2, set(), False),
        events.Skip(r2),
    ])

    # skip r1
    log.clear()
    r1._should_update = False
    r2._should_update = True

    make([r2], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Skip(r1),

        ('should_update', r2, set(), False),
        events.Start(r2),
        ('preprocess', r2),
        ('method',),
        ('postprocess', r2, True),
        events.Done(r2),
    ])


def test_dryrun():
    r1 = MockRule([], (), {}, lambda: None)
    r2 = MockRule([r1], (), {}, lambda: None)

    # dry-run r1
    log.clear()
    make([r1], True, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), True), events.DryRun(r1)
    ])

    # dry-run r2
    log.clear()
    make([r2], True, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), True), events.DryRun(r1),
        ('should_update', r2, {r1}, True), events.DryRun(r2),
    ])


def test_should_update_error():
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, should_update=e)

    log.clear()
    make([r1], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.UpdateCheckError(r1, e),
        events.StopOnFail()
    ])
    

def test_preprocess_error():
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, preprocess_err=e)

    log.clear()
    make([r1], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        events.PreProcError(r1, e),
        events.StopOnFail(),
    ])


def test_exec_error():
    e = Exception()
    def raiser():
        raise e
    r1 = MockRule([], (), {}, raiser)

    log.clear()
    make([r1], False, False, callback)
    print(log)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        events.ExecError(r1, e),
        ('postprocess', r1, False),
        events.StopOnFail()
    ])


def test_postprocess_error(tmp_path):
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, postprocess_err=e)

    log.clear()
    make([r1], False, False, callback)
    assert_same_log(log, [
        ('should_update', r1, set(), False),
        events.Start(r1),
        ('preprocess', r1),
        # method
        ('postprocess', r1, True),
        events.PostProcError(r1, e),
        events.StopOnFail()
    ])
