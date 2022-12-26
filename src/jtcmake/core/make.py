from __future__ import annotations
from multiprocessing.pool import Pool
import traceback
import enum
from typing import (
    Callable,
    List,
    Literal,
    NamedTuple,
    Optional,
    Set,
    Sequence,
    TypeVar,
)

from . import events
from .abc import IRule, IEvent, UpdateResults


class Result(enum.Enum):
    Update = 1
    Skip = 2
    Fail = 3
    Fatal = 4


SummaryKey = Literal["update", "skip", "fail", "discard"]


class MakeSummary(NamedTuple):
    total: int  # planned to be update
    update: int  # actually updated (method called)
    skip: int  # "nothing to do with ..."
    fail: int  # failed ones
    discard: int  # not checked because of abort
    detail: dict[int, SummaryKey]

    @classmethod
    def create(cls, detail: dict[int, SummaryKey]):
        a: dict[SummaryKey, int] = {
            "update": 0,
            "skip": 0,
            "fail": 0,
            "discard": 0,
        }
        for _, key in detail.items():
            a[key] += 1
        return cls(**a, total=len(detail), detail=detail)


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


_T_Rule = TypeVar("_T_Rule", bound=IRule)


def make(
    id2rule: Sequence[_T_Rule],
    ids: Sequence[int],
    dry_run: bool,
    keep_going: bool,
    callback: Callable[[IEvent[_T_Rule]], None],
):
    if len(ids) == 0:
        return MakeSummary(
            total=0, update=0, skip=0, fail=0, discard=0, detail={}
        )

    main_ids = set(ids)

    target_ids = _toplogical_sort(id2rule, ids)

    failed_ids: Set[int] = set()  # includes discarded ones
    updated_ids: Set[int] = set()

    summary: dict[int, SummaryKey] = {}

    for i in target_ids:
        r = id2rule[i]

        if any(dep in failed_ids for dep in r.deps):
            failed_ids.add(i)
            continue

        par_updated = any(dep in updated_ids for dep in r.deps)

        try:
            result = process_rule(
                r, dry_run, par_updated, i in main_ids, callback, None
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
            summary[i] = "update"
        elif result == Result.Fail:
            failed_ids.add(i)
            summary[i] = "fail"
            if not keep_going:
                try:
                    callback(events.StopOnFail())
                except Exception:
                    traceback.print_exc()
                break
        elif result == Result.Fatal:
            failed_ids.add(i)
            summary[i] = "fail"
            break
        else:
            assert result == Result.Skip
            summary[i] = "skip"

    for i in target_ids:
        if i not in summary:
            summary[i] = "discard"

    return MakeSummary.create(summary)


def process_rule(
    rule: _T_Rule,
    dry_run: bool,
    par_updated: bool,
    is_main: bool,
    callback: Callable[[IEvent[_T_Rule]], None],
    pool: Optional[Pool],
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
        rule.preprocess()
    except Exception as e:
        callback(events.PreProcError(rule, e))
        return Result.Fail

    try:
        if pool is None:
            rule.method()
            succ = True
        else:
            pool.apply(rule.method)
            succ = True
    except Exception as e:
        callback(events.ExecError(rule, e))
        succ = False
    except KeyboardInterrupt:
        try:
            rule.postprocess(False)
        except Exception:
            pass

        raise KeyboardInterrupt()

    try:
        rule.postprocess(succ)
    except Exception as e:
        callback(events.PostProcError(rule, e))
        return Result.Fail

    if succ:
        callback(events.Done(rule))
        return Result.Update
    else:
        return Result.Fail
