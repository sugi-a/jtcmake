import os, sys, re, traceback, inspect, abc, time, enum
from threading import Condition, Thread
from collections import defaultdict, deque, namedtuple

from . import events
from .abc import IRule


class Result(enum.Enum):
    Update = 1
    Skip = 2
    Fail = 3


MakeSummary = namedtuple(
    "MakeSummary",
    [
        "total",  # planned to be update
        "update",  # actually updated (method called)
        "skip",  # "nothing to do with ..."
        "fail",  # failed ones
        "discard",  # not checked because of abort
    ],
)


def _toplogical_sort(id2rule, seed_ids):
    added = set()
    res = []

    def rec(i):
        if i in added:
            return

        added.add(i)

        for dep in id2rule[i].deplist:
            rec(dep)

        res.append(i)

    for i in seed_ids:
        rec(i)

    return res


def make(
    id2rule,
    ids,
    dry_run,
    keep_going,
    callback,
):
    if len(ids) == 0:
        return MakeSummary(total=0, update=0, skip=0, fail=0, discard=0)

    main_ids = set(ids)

    taskq = _toplogical_sort(id2rule, ids)

    failed_ids = set()  # includes discarded ones
    updated_ids = set()
    nskips = 0  # for stats report
    nfails = 0  # for stats report

    for i in taskq:
        r = id2rule[i]

        if any(dep in failed_ids for dep in r.deplist):
            failed_ids.add(i)
            continue

        par_updated = any(dep in updated_ids for dep in r.deplist)

        try:
            result = process_rule(
                r, dry_run, par_updated, i in main_ids, callback
            )
        except Exception as e:
            try:
                callback(events.FatalError(r, e))
            except Exception:
                traceback.print_exc()
                pass
            break

        if result == Result.Update:
            updated_ids.add(i)
        elif result == Result.Fail:
            nfails += 1
            failed_ids.add(i)
            if not keep_going:
                try:
                    callback(events.StopOnFail())
                except Exception:
                    traceback.print_exc()
                break
        else:
            assert result == Result.Skip
            nskips += 1

    return MakeSummary(
        total=len(taskq),
        update=len(updated_ids),
        skip=nskips,
        fail=nfails,
        discard=len(taskq) - (len(updated_ids) + nskips + nfails),
    )


def process_rule(rule, dry_run, par_updated, is_main, callback):
    if dry_run:
        try:
            should_update = rule.should_update(par_updated, True)
        except Exception as e:
            callback(events.UpdateCheckError(rule, e))
            return Result.Fail

        if should_update:
            callback(events.DryRun(rule))
            return Result.Update
        else:
            callback(events.Skip(rule, is_main))
            return Result.Skip

    try:
        should_update = rule.should_update(par_updated, False)
    except Exception as e:
        callback(events.UpdateCheckError(rule, e))
        return Result.Fail

    if not should_update:
        callback(events.Skip(rule, is_main))
        return Result.Skip

    callback(events.Start(rule))

    try:
        rule.preprocess(callback)
    except Exception as e:
        callback(events.PreProcError(rule, e))
        return Result.Fail

    try:
        rule.method(*rule.args, **rule.kwargs)
        succ = True
    except Exception as e:
        callback(events.ExecError(rule, e))
        succ = False
    except KeyboardInterrupt as e:
        try:
            rule.postprocess(callback, succ)
        except:
            pass

        raise KeyboardInterrupt()

    try:
        rule.postprocess(callback, succ)
    except Exception as e:
        callback(events.PostProcError(rule, e))
        return Result.Fail

    if succ:
        callback(events.Done(rule))
        return Result.Update
    else:
        return Result.Fail
