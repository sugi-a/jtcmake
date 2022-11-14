from __future__ import annotations
from multiprocessing.context import SpawnContext
import sys
import traceback
from multiprocessing import get_context
from threading import Thread, Condition, Lock

from collections import defaultdict
from typing import (
    Dict,
    Mapping,
    Set,
    Tuple,
    Callable,
    List,
    Union,
    Sequence,
)

from . import events
from .abc import IRule, IEvent
from .make import process_rule, Result, MakeSummary


def _collect_rules(
    id2rule: Sequence[IRule], seed_ids: Sequence[int]
) -> Tuple[List[int], Dict[int, Set[int]]]:
    """collect rules on which seed rules depend"""
    ids: Set[int] = set()
    b2a: Dict[int, Set[int]] = defaultdict(set)  # dict<ID, ID> before to after

    def find_deps(i: int):
        if i in ids:
            return

        ids.add(i)

        for dep in id2rule[i].deps:
            find_deps(dep)
            b2a[dep].add(i)

    for i in seed_ids:
        find_deps(i)

    return list(ids), b2a


def make_mp_spawn(
    id2rule: Sequence[IRule],
    ids: Sequence[int],
    dry_run: bool,
    keep_going: bool,
    callback: Callable[[IEvent], None],
    njobs: int,
):
    if len(ids) == 0:
        return MakeSummary(total=0, update=0, skip=0, fail=0, discard=0)

    assert njobs >= 2

    # Use the process starting method 'spawn' regardless of OS
    ctx = get_context("spawn")

    # Not very confident but this useless Pool seems necessary for later
    # use of Pool in threads to work reliably.
    with ctx.Pool(1):
        pass

    # Gather relevant rules
    main_ids = ids
    ids, b2a = _collect_rules(id2rule, main_ids)

    dep_cnt = {i: len(id2rule[i].deps) for i in ids}

    # Check inter-process transferability
    rules = [id2rule[i] for i in ids]
    method_objs = [(r.method, r.args, r.kwargs) for r in rules]
    sendable = _test_interproc_portabability(method_objs, ctx)
    _log_sendable_stats(sendable)
    sendable = {ids[j]: sendable[j] for j in range(len(ids))}

    # state vars
    updated_ids: Set[int] = set()  # rules processed and not skipped

    nskips = 0  # for stats report
    nfails = 0  # for stats report

    job_q: List[int] = []  # FIFO: visit nodes in depth-first order

    nidles = njobs  # #idle slots

    stop = False

    cv = Condition()  # for the above state vars
    cb_lock = Lock()  # used when callback()

    # Add rules with no dependencies to the job queue
    for i in ids:
        if dep_cnt[i] == 0:
            job_q.append(i)

    def get_job() -> Union[int, None]:
        nonlocal nidles

        with cv:
            while True:
                if stop:
                    return None
                elif len(job_q) != 0:
                    nidles -= 1
                    assert nidles >= 0
                    return job_q.pop()
                elif nidles == njobs:
                    return None

                cv.wait()

    def set_result(i: int, res: Union[Result, None]):
        nonlocal stop, nidles, nskips, nfails

        with cv:
            nidles += 1
            assert nidles <= njobs

            if res is None:  # fatal error
                nfails += 1
                stop = True
            elif res == Result.Fail:
                nfails += 1
                if not keep_going:
                    stop = True
            else:
                if res == Result.Update:
                    updated_ids.add(i)
                else:
                    nskips += 1

                for nxt in b2a[i]:
                    dep_cnt[nxt] -= 1
                    assert dep_cnt[nxt] >= 0

                    if dep_cnt[nxt] == 0:
                        job_q.append(nxt)

            cv.notify_all()

    def callback_(e: IEvent):
        with cb_lock:
            callback(e)

    args = (
        ctx,
        get_job,
        set_result,
        id2rule,
        updated_ids,
        main_ids,
        sendable,
        dry_run,
        callback_,
    )

    threads = [Thread(target=worker, args=args) for _ in range(njobs)]

    for t in threads:
        t.start()

    try:
        for t in threads:
            t.join()
    except Exception:
        pass
    finally:
        with cv:
            stop = True
            cv.notify_all()

    return MakeSummary(
        total=len(ids),
        update=len(updated_ids),
        skip=nskips,
        fail=nfails,
        discard=len(ids) - (len(updated_ids) + nskips + nfails),
    )


def worker(
    ctx: SpawnContext,
    get_job: Callable[[], Union[int, None]],
    set_result: Callable[[int, Union[Result, None]], None],
    id2rule: List[IRule],
    updated_ids: Set[int],
    main_ids: Set[int],
    sendable: Mapping[int, bool],
    dry_run: bool,
    callback: Callable[[IEvent], None],
):
    with ctx.Pool(1) as pool:
        while True:
            i = get_job()

            if i is None:
                return

            rule = id2rule[i]

            res = None

            try:
                par_updated = any(dep in updated_ids for dep in rule.deps)
                args = (rule, dry_run, par_updated, i in main_ids, callback)

                if sendable[i]:
                    res = process_rule(*args, pool)
                else:
                    res = process_rule(*args, None)
            except (Exception, KeyboardInterrupt) as e:
                traceback.print_exc()
                callback(events.FatalError(rule, e))
            finally:
                set_result(i, res)

                if res is None:
                    return


def _test_interproc_portabability(
    objs: Sequence[object], ctx: SpawnContext
) -> List[bool]:
    n = len(objs)
    picklable = [True] * n

    sys.stderr.write("Checking picklability\n")

    with ctx.Pool(1) as pool:
        for i, obj in enumerate(objs):
            try:
                pool.apply(_dummy_func, (obj,))
            except Exception:
                picklable[i] = False

    return picklable


def _dummy_func(_: object) -> bool:
    ...


def _log_sendable_stats(sendables: Sequence[bool]):
    n = len(sendables)
    ok = sum(1 for x in sendables if x)
    ng = n - ok

    if ng > 0:
        sys.stderr.write(
            f"{ng} of {n} Rules will be executed using threads in the main "
            "process instad of using multi-processing. This is because "
            "their method/args/kwargs contain some objects that cannot be "
            "transfered to child processes.\n"
        )
