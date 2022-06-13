import os, sys, re, traceback, inspect, abc, time
from threading import Condition, Thread
from collections import defaultdict, deque

from .decls import NOP, RuleMemo

class DryRunInfo:
    def __init__(self):
        self.pups = set() # potentially updated paths


class Events:
    class EventBase(abc.ABC):
        def __init__(self, rule):
            self._rule = rule

        def rule(self):
            return self._rule

    class ErrorEventBase(EventBase):
        def __init__(self, rule, error):
            super().__init__(rule)
            self._error = error

        def err(self):
            return self._error


    class UpdateCheckError(ErrorEventBase):
        pass

    class Skip(EventBase):
        pass

    class MkdirError(ErrorEventBase):
        pass

    class Start(EventBase):
        pass

    class ExecError(ErrorEventBase):
        pass

    class Done(EventBase):
        pass

    class FatalError(ErrorEventBase):
        pass

    class DryRun(EventBase):
        pass

    class StopOnFail(EventBase):
        pass

    class SkipReadonly(EventBase):
        pass

    class PostProcError(ErrorEventBase):
        pass


def make(rules, dry_run, stop_on_fail, callback):
    if len(rules) == 0:
        return

    dry_run_info = DryRunInfo() if dry_run else None

    rules = set(rules)

    added = set()
    taskq = []

    # topological sort
    def rec(t):
        if t in added:
            return

        added.add(t)

        for dept in t.depset:
            rec(dept)

        taskq.append(t)

    for rule in rules:
        rec(rule)

    failed_rule = set()

    for t in taskq:
        if any(dept in failed_rule for dept in t.depset):
            failed_rule.add(t)
            continue

        try:
            result = process_rule(t, dry_run_info, callback)
        except Exception as e:
            traceback.print_exc()
            callback(Events.FatalError(t, e))
            return

        if not result:
            failed_rule.add(t)
            if stop_on_fail:
                callback(Events.StopOnFail(None))
                return
        

def process_rule(rule, dry_run_info, callback):
    if rule.method is NOP:
        callback(Events.SkipReadonly(rule))
        return True

    if dry_run_info is not None:
        # dry-run
        try:
            should_update = rule.should_update_dryrun(dry_run_info.pups)
        except Exception as e:
            traceback.print_exc()
            callback(Events.UpdateCheckError(rule, e))
            return False

        if should_update:
            callback(Events.DryRun(rule))
            dry_run_info.pups.update(rule.opaths)
        else:
            callback(Events.Skip(rule))
        return True

    try:
        should_update = rule.should_update()
    except Exception as e:
        traceback.print_exc()
        callback(Events.UpdateCheckError(rule, e))
        return False

    if not should_update:
        callback(Events.Skip(rule))
        return True

    for p in rule.opaths:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
        except Exception as e:
            callback(Events.MkdirError(rule, e))

    callback(Events.Start(rule))

    try:
        rule.method(*rule.args, **rule.kwargs)
    except Exception as e:
        traceback.print_exc()
        callback(Events.ExecError(rule, e))
        for p in rule.opaths:
            try:
                os.utime(p, (time.time(), 0))
            except Exception:
                pass
        return False

    try:
        rule.post_process()
    except Exception as e:
        callback(Events.PostProcError(rule, e))
        return False

    callback(Events.Done(rule))

    return True


def make_multi_thread(rules, dry_run, stop_on_fail, nthreads, callback):
    assert isinstance(nthreads, int) and nthreads > 0

    dry_run_info = DryRunInfo() if dry_run else None

    if len(rules) == 0:
        return

    rules = set(rules)

    b2a = defaultdict(set) # before to after
    dep_cnt = {}

    def rec(t):
        if t in dep_cnt:
            return

        dep_cnt[t] = len(t.depset)

        for dept in t.depset:
            b2a[dept].add(t)
            rec(dept)
    
    for t in rules:
        rec(t)

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

            if res == 0:
                stop = True
            elif res == 2:
                if stop_on_fail:
                    stop = True
            else:
                for nxt in b2a[rule]:
                    dep_cnt[nxt] -= 1
                    if dep_cnt[nxt] == 0:
                        taskq.append(nxt)

            cv.notify_all()
            

    args = (get_rule_fn, set_result_fn, dry_run_info, callback)
    threads = [Thread(target=worker, args=(*args, i), name=f'lightmake{i}') for i in range(nthreads)]

    for t in threads: t.start()
    for t in threads: t.join()

    if stop:
        callback(Events.StopOnFail(None))


def worker(get_rule_fn, set_result_fn, dry_run_info, callback, thread_id):
    while True:
        rule = get_rule_fn()

        if rule is None:
            return
        
        res = 0

        try:
            if process_rule(rule, dry_run_info, callback):
                res = 1
            else:
                res = 2
        except Exception as e:
            traceback.print_exc()
            callback(Events.FatalError(rule, e))
        finally:
            set_result_fn(rule, res)

