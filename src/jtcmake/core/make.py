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


def make_multi_thread(
    rules,
    dry_run,
    keep_going,
    nthreads,
    callback
    ):
    if nthreads < 1:
        raise ValueError('nthreads must be greater than 0')

    if len(rules) == 0:
        return

    direct_targets = set(rules)

    b2a = defaultdict(set) # before to after
    dep_cnt = {}

    def rec(t):
        if t in dep_cnt:
            return

        dep_cnt[t] = len(t.deplist)

        for dept in t.deplist:
            b2a[dept].add(t)
            rec(dept)
    
    for t in rules:
        rec(t)

    updated_rules = set()

    cv = Condition()
    taskq = deque(t for t,c in dep_cnt.items() if c == 0)
    processing = set()
    stop = False

    def get_rule_fn():
        with cv:
            while len(taskq) == 0 and len(processing) != 0 and not stop:
                cv.wait()

            if stop:
                return None

            if len(taskq) == 0 and len(processing) == 0:
                return None

            r = taskq.popleft()
            processing.add(r)

            return r

    def set_result_fn(rule, res):
        nonlocal stop
        with cv:
            processing.remove(rule)

            if res is None:
                stop = True
            elif res == Result.Fail:
                if not keep_going:
                    stop = True
            else:
                if res == Result.Update:
                    updated_rules.add(res)

                for nxt in b2a[rule]:
                    dep_cnt[nxt] -= 1
                    if dep_cnt[nxt] == 0:
                        taskq.append(nxt)

            cv.notify_all()
            

    args = (
        get_rule_fn, set_result_fn,
        updated_rules, direct_targets, dry_run, callback)
    threads = [
        Thread(target=worker, args=(*args,), name=f'lightmake{i}')
        for i in range(nthreads)
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    if stop:
        callback(events.StopOnFail(None))


def worker(
    get_rule_fn,
    set_result_fn,
    updated_rules,
    direct_targets,
    dry_run,
    callback,
    ):
    while True:
        rule = get_rule_fn()

        if rule is None:
            return
        
        res = None

        try:
            res = process_rule(
                rule, dry_run, updated_rules, direct_targets, callback
            )
        except Exception as e:
            traceback.print_exc()
            callback(events.FatalError(rule, e))
        finally:
            set_result_fn(rule, res)

