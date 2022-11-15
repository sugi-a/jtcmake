from typing import Any, Callable, Iterable, List, Optional
import pytest

from jtcmake.core.abc import IEvent, IRule, UpdateResult, UpdateResults
from jtcmake.core.make import make, MakeSummary
from jtcmake.core.make_mp import make_mp_spawn
from jtcmake.core import events


def fail(*args: object, exc: Optional[Exception] = None, **kwargs: object):
    if exc is None:
        exc = Exception()
    raise exc


def assert_same_event(e1: IEvent[IRule], e2: IEvent[IRule]):
    assert type(e1) == type(e2)
    assert e1.__dict__ == e2.__dict__


def assert_same_log_item(x1: object, x2: object):
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


log: List[object] = []


def callback(event: IEvent[IRule]):
    log.append(event)


class MockRule(IRule):
    def __init__(
        self,
        deplist: Iterable[int],
        method: Callable[[], object],
        check_update: UpdateResult = UpdateResults.Necessary(),
        preprocess_err: Optional[Exception] = None,
        postprocess_err: Optional[Exception] = None,
    ):
        self._deplist = set(deplist)
        self.check_update_ = check_update
        self._method = method
        self._preprocess_err = preprocess_err
        self._postprocess_err = postprocess_err

    def check_update(self, par_updated: bool, dry_run: bool):
        log.append(("check_update", self, par_updated, dry_run))
        if isinstance(self.check_update_, Exception):
            raise self.check_update_
        return self.check_update_

    def preprocess(self):
        log.append(("preprocess", self))
        if self._preprocess_err is not None:
            raise self._preprocess_err

    def postprocess(self, succ: bool):
        log.append(("postprocess", self, succ))
        if self._postprocess_err is not None:
            raise self._postprocess_err

    @property
    def method(self):
        return self._method

    @property
    def deps(self):
        return self._deplist

    @property
    def name(self):
        return "mock"


@pytest.mark.parametrize("mp", [False, True])
def test_basic(mp: bool):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args: Any, **kwargs: Any):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    def method():
        log.append(("method",))

    r1 = MockRule([], method)
    r2 = MockRule([0], method)

    id2rule = [r1, r2]

    # pass both
    log.clear()
    res = make_(id2rule, [0, 1], False, False, callback)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            ("method",),
            ("postprocess", r1, True),
            events.Done(r1),
            ("check_update", r2, True, False),
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
            ("check_update", r1, False, False),
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
            ("check_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            ("method",),
            ("postprocess", r1, True),
            events.Done(r1),
            ("check_update", r2, True, False),
            events.Start(r2),
            ("preprocess", r2),
            ("method",),
            ("postprocess", r2, True),
            events.Done(r2),
        ],
    )


@pytest.mark.parametrize("mp", [False, True])
def test_skip(mp: bool):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args: Any, **kwargs: Any):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    def method():
        log.append(("method",))

    r1 = MockRule([], method)
    r2 = MockRule([1], method)

    id2rule = {1: r1, 2: r2}

    # skip both
    log.clear()
    r1.check_update_ = UpdateResults.UpToDate()
    r2.check_update_ = UpdateResults.UpToDate()

    res = make_(id2rule, [2], False, False, callback)

    assert res == MakeSummary(total=2, update=0, skip=2, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Skip(r1, False),
            ("check_update", r2, False, False),
            events.Skip(r2, True),
        ],
    )

    # skip r1
    log.clear()
    r1.check_update_ = UpdateResults.UpToDate()
    r2.check_update_ = UpdateResults.Necessary()

    res = make_(id2rule, [2], False, False, callback)

    assert res == MakeSummary(total=2, update=1, skip=1, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Skip(r1, False),
            ("check_update", r2, False, False),
            events.Start(r2),
            ("preprocess", r2),
            ("method",),
            ("postprocess", r2, True),
            events.Done(r2),
        ],
    )


@pytest.mark.parametrize("mp", [False, True])
def test_dryrun(mp: bool):
    """
    * Two rules r1 and r2, where r2 depends on r1
    * Single task mode and multi task mode must yield the same results
    """

    def make_(*args: Any, **kwargs: Any):
        if mp:
            return make_mp_spawn(*args, **kwargs, njobs=2)
        else:
            return make(*args, **kwargs)

    r1 = MockRule([], lambda: None)
    r2 = MockRule([1], lambda: None)

    id2rule = {1: r1, 2: r2}

    # dry-run r1
    log.clear()
    res = make_(id2rule, [1], True, False, callback)

    assert res == MakeSummary(total=1, update=1, skip=0, fail=0, discard=0)
    assert_same_log(log, [("check_update", r1, False, True), events.DryRun(r1)])

    # dry-run r2
    log.clear()
    res = make_(id2rule, [2], True, False, callback)

    assert res == MakeSummary(total=2, update=2, skip=0, fail=0, discard=0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, True),
            events.DryRun(r1),
            ("check_update", r2, True, True),
            events.DryRun(r2),
        ],
    )


def test_preprocess_error():
    e = Exception()
    r1 = MockRule([], lambda: None, preprocess_err=e)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
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

    r1 = MockRule([], raiser)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            events.ExecError(r1, e),
            ("postprocess", r1, False),
            events.StopOnFail(),
        ],
    )


def test_postprocess_error():
    e = Exception()
    r1 = MockRule([], lambda: None, postprocess_err=e)

    id2rule = [r1]

    log.clear()
    res = make(id2rule, [0], False, False, callback)

    assert res == MakeSummary(1, 0, 0, 1, 0)
    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            # method
            ("postprocess", r1, True),
            events.PostProcError(r1, e),
            events.StopOnFail(),
        ],
    )


def test_keyboard_interrupt():
    # raise KeyboardInterrupt while executing method
    e = KeyboardInterrupt()

    def _func():
        raise e

    r1 = MockRule([], _func)
    id2rule = [r1]
    log.clear()

    with pytest.raises(KeyboardInterrupt):
        make(id2rule, [0], False, False, callback)

    assert_same_log(
        log,
        [
            ("check_update", r1, False, False),
            events.Start(r1),
            ("preprocess", r1),
            # method
            ("postprocess", r1, False),
        ],
    )
