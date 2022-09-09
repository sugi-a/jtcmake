import sys, os, shutil
import pytest

from jtcmake.core.abc import IEvent, IRule
from jtcmake.core.make import make, MakeSummary
from jtcmake.core.make_mp import make_mp_spawn
from jtcmake.core import events


def fail(*args, exc=None, **kwargs):
    if exc is None:
        exc = Exception()
    raise exc


def assert_same_event(e1, e2):
    assert type(e1) == type(e2)
    assert e1.__dict__ == e2.__dict__


def assert_same_log_item(x1, x2):
    if isinstance(x1, IEvent):
        assert_same_event(x1, x2)
    else:
        assert len(x1) == len(x2)
        for u, v in zip(x1, x2):
            if isinstance(u, IEvent):
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
        self,
        deplist,
        args,
        kwargs,
        method,
        should_update=True,
        preprocess_err=None,
        postprocess_err=None,
    ):
        self._deplist = deplist
        self._should_update = should_update
        self._args = args
        self._kwargs = kwargs
        self._method = method
        self._preprocess_err = preprocess_err
        self._postprocess_err = postprocess_err

    def should_update(self, par_updated, dry_run):
        log.append(("should_update", self, par_updated, dry_run))
        if isinstance(self._should_update, Exception):
            raise self._should_update
        return self._should_update

    def preprocess(self, callback):
        log.append(("preprocess", self))
        if self._preprocess_err is not None:
            raise self._preprocess_err

    def postprocess(self, callback, succ):
        log.append(("postprocess", self, succ))
        if self._postprocess_err is not None:
            raise self._postprocess_err

    @property
    def method(self):
        return self._method

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwargs

    @property
    def deplist(self):
        return self._deplist


@pytest.mark.parametrize("mp", [False, True])
def test_basic(mp):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args, **kwargs):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    args, kwargs = (object(),), {"a": object()}

    def method(*args_, **kwargs_):
        assert args_ == args
        assert kwargs_ == kwargs
        log.append(("method",))

    r1 = MockRule([], args, kwargs, method)
    r2 = MockRule([0], args, kwargs, method)

    id2rule = [r1, r2]

    # pass both
    log.clear()
    res = make_(id2rule, [0, 1], False, False, callback)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            ("method",),
            ("postprocess", r1, True),
            events.Done(r1),
            ("should_update", r2, True, False),
            events.Start(r2),
            ("preprocess", r2),
            ("method",),
            ("postprocess", r2, True),
            events.Done(r2),
        ],
    )

    # pass r1
    log.clear()
    res = make_(id2rule, [0], False, False, callback)

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            ("method",),
            ("postprocess", r1, True),
            events.Done(r1),
        ],
    )

    # pass r2
    log.clear()
    res = make_(id2rule, [1], False, False, callback)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            ("method",),
            ("postprocess", r1, True),
            events.Done(r1),
            ("should_update", r2, True, False),
            events.Start(r2),
            ("preprocess", r2),
            ("method",),
            ("postprocess", r2, True),
            events.Done(r2),
        ],
    )


@pytest.mark.parametrize("mp", [False, True])
def test_skip(mp):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args, **kwargs):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    args, kwargs = (object(),), {"a": object()}

    def method(*args_, **kwargs_):
        assert args_ == args
        assert kwargs_ == kwargs
        log.append(("method",))

    r1 = MockRule([], args, kwargs, method)
    r2 = MockRule([1], args, kwargs, method)

    id2rule = {1: r1, 2: r2}

    # skip both
    log.clear()
    r1._should_update = False
    r2._should_update = False

    res = make_(id2rule, [2], False, False, callback)

    assert res == MakeSummary(total=2, update=0, skip=2, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Skip(r1, False),
            ("should_update", r2, False, False),
            events.Skip(r2, True),
        ],
    )

    # skip r1
    log.clear()
    r1._should_update = False
    r2._should_update = True

    res = make_(id2rule, [2], False, False, callback)

    assert res == MakeSummary(total=2, update=1, skip=1, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Skip(r1, False),
            ("should_update", r2, False, False),
            events.Start(r2),
            ("preprocess", r2),
            ("method",),
            ("postprocess", r2, True),
            events.Done(r2),
        ],
    )


@pytest.mark.parametrize("mp", [False, True])
def test_dryrun(mp):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args, **kwargs):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    r1 = MockRule([], (), {}, lambda: None)
    r2 = MockRule([1], (), {}, lambda: None)

    id2rule = {1: r1, 2: r2}

    # dry-run r1
    log.clear()
    res = make_(id2rule, [1], True, False, callback)

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert_same_log(
        log, [("should_update", r1, False, True), events.DryRun(r1)]
    )

    # dry-run r2
    log.clear()
    res = make_(id2rule, [2], True, False, callback)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, True),
            events.DryRun(r1),
            ("should_update", r2, True, True),
            events.DryRun(r2),
        ],
    )


def test_should_update_error():
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, should_update=e)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.UpdateCheckError(r1, e),
            events.StopOnFail(),
        ],
    )


def test_preprocess_error():
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, preprocess_err=e)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            events.PreProcError(r1, e),
            events.StopOnFail(),
        ],
    )


def test_exec_error():
    e = Exception()

    def raiser():
        raise e

    r1 = MockRule([], (), {}, raiser)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            events.ExecError(r1, e),
            ("postprocess", r1, False),
            events.StopOnFail(),
        ],
    )


def test_postprocess_error(tmp_path):
    e = Exception()
    r1 = MockRule([], (), {}, lambda: None, postprocess_err=e)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            # method
            ("postprocess", r1, True),
            events.PostProcError(r1, e),
            events.StopOnFail(),
        ],
    )


def test_keyboard_interrupt(tmp_path):
    # raise KeyboardInterrupt while executing method
    e = KeyboardInterrupt()

    def _func():
        raise e

    r1 = MockRule([], (), {}, _func)
    id2rule = [r1]
    log.clear()

    with pytest.raises(KeyboardInterrupt):
        res = make(id2rule, [0], False, False, callback)

    assert_same_log(
        log,
        [
            ("should_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            # method
            ("postprocess", r1, True),
        ],
    )
