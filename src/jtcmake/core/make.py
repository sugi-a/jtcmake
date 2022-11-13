import traceback
import enum
from typing import Callable, List, NamedTuple, Set, Sequence

from . import events
from .abc import IRule, IEvent, UpdateResults


class Result(enum.Enum):
    Update = 1
    Skip = 2
    Fail = 3
    Fatal = 4


class MakeSummary(NamedTuple):
    total: int  # planned to be update
    update: int  # actually updated (method called)
    skip: int  # "nothing to do with ..."
    fail: int  # failed ones
    discard: int  # not checked because of abort


def _toplogical_sort(
    id2rule: Sequence[IRule], seed_ids: Sequence[int]
) -> List[int]:
    added: Set[int] = set()
    res: List[int] = []

    def rec(i: int):
        if i in added:
            return

        added.add(i)

        for dep in id2rule[i].deps:
            rec(dep)

        res.append(i)

    for i in seed_ids:
        rec(i)

    return res


def make(
    id2rule: Sequence[IRule],
    ids: Sequence[int],
    dry_run: bool,
    keep_going: bool,
    callback: Callable[[IEvent], None],
):
    if len(ids) == 0:
        return MakeSummary(total=0, update=0, skip=0, fail=0, discard=0)

    main_ids = set(ids)

    taskq = _toplogical_sort(id2rule, ids)

    failed_ids: Set[int] = set()  # includes discarded ones
    updated_ids: Set[int] = set()
    nskips: int = 0  # for stats report
    nfails: int = 0  # for stats report

    for i in taskq:
        r = id2rule[i]

        if any(dep in failed_ids for dep in r.deps):
            failed_ids.add(i)
            continue

        par_updated = any(dep in updated_ids for dep in r.deps)

        try:
            result = process_rule(
                r, dry_run, par_updated, i in main_ids, callback
            )
        except Exception as e:
            result = Result.Fatal
            try:
                callback(events.FatalError(r, e))
            except Exception:
                traceback.print_exc()
                pass

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
        elif result == Result.Fatal:
            nfails += 1
            failed_ids.add(i)
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


def process_rule(
    rule: IRule,
    dry_run: bool,
    par_updated: bool,
    is_main: bool,
    callback: Callable[[IEvent], None],
):
    if dry_run:
        res = rule.check_update(par_updated, True)

        if isinstance(res, UpdateResults.Infeasible):
            callback(events.UpdateInfeasible(rule, res.reason))
            return Result.Fail
        elif isinstance(
            res, (UpdateResults.Necessary, UpdateResults.PossiblyNecessary)
        ):
            callback(events.DryRun(rule))
            return Result.Update
        else:
            callback(events.Skip(rule, is_main))
            return Result.Skip

    res = rule.check_update(par_updated, False)

    if isinstance(res, UpdateResults.Infeasible):
        callback(events.UpdateInfeasible(rule, res.reason))
        return Result.Fail
    elif isinstance(res, UpdateResults.UpToDate):
        callback(events.Skip(rule, is_main))
        return Result.Skip
    elif not isinstance(res, UpdateResults.Necessary):
        raise Exception(f"Internal error: unexpected result {res}")

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
    except KeyboardInterrupt:
        try:
            rule.postprocess(callback, False)
        except Exception:
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
