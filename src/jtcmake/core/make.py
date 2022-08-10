import os, sys, re, traceback, inspect, abc, time, enum
from threading import Condition, Thread
from collections import defaultdict, deque

from . import events
from .rule import Event, IRule

class Result(enum.Enum):
    Update = 1
    Skip = 2
    Fail = 3


def make(
    rules,
    dry_run,
    keep_going,
    callback,
    ):
    if len(rules) == 0:
        return

    direct_targets = set(rules)

    added = set()
    taskq = []

    # topological sort
    def rec(t):
        if t in added:
            return

        added.add(t)

        for dept in t.deplist:
            rec(dept)

        taskq.append(t)

    for rule in rules:
        rec(rule)

    failed_rule = set()
    updated_rules = set()

    for t in taskq:
        if any(dept in failed_rule for dept in t.deplist):
            failed_rule.add(t)
            continue

        try:
            result = process_rule(
                t, dry_run, updated_rules, direct_targets, callback
            )
        except Exception as e:
            traceback.print_exc()
            callback(events.FatalError(t, e))
            return False

        if result == Result.Update:
            updated_rules.add(t)
        elif result == Result.Fail:
            failed_rule.add(t)
            if not keep_going:
                callback(events.StopOnFail())
                return False

    return True
        

def process_rule(
    rule,
    dry_run,
    updated_rules,
    direct_targets,
    callback
    ):
    if dry_run:
        try:
            should_update = rule.should_update(updated_rules, True)
        except Exception as e:
            traceback.print_exc()
            callback(events.UpdateCheckError(rule, e))
            return Result.Fail

        if should_update:
            callback(events.DryRun(rule))
            return Result.Update
        else:
            callback(events.Skip(rule))
            return Result.Skip

    try:
        should_update = rule.should_update(updated_rules, False)
    except Exception as e:
        traceback.print_exc()
        callback(events.UpdateCheckError(rule, e))
        return Result.Fail

    if not should_update:
        callback(events.Skip(rule, rule in direct_targets))
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
        traceback.print_exc()
        callback(events.ExecError(rule, e))
        succ = False

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

