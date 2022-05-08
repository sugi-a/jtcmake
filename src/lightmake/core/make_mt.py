import sys, os, traceback, inspect
from threading import Condition, Thread
from collections import defaultdict, deque

from .make import process_rule

def make_multi_thread(rules, dry_run, stop_on_fail, writer, nthreads):
    assert isinstance(nthreads, int) and nthreads > 0

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

            return r, r not in rules

    def set_result_fn(rule, res):
        nonlocal stop
        with cv:
            processing.remove(rule)

            if not res:
                if stop_on_fail:
                    stop = True
            else:
                for nxt in b2a[rule]:
                    dep_cnt[nxt] -= 1
                    if dep_cnt[nxt] == 0:
                        taskq.append(nxt)

            cv.notify_all()
            

    args = (get_rule_fn, set_result_fn, dry_run, writer)
    threads = [Thread(target=worker, args=(*args, i), name=f'lightmake{i}') for i in range(nthreads)]

    for t in threads: t.start()
    for t in threads: t.join()

    if stop:
        writer('Stopped by a failure\n', logkind='warning')


def worker(get_rule_fn, set_result_fn, dry_run, writer, thread_id):
    while True:
        t = get_rule_fn()

        if t is None:
            return

        rule, silent_skip = t
        
        res = False

        try:
            res = process_rule(rule, dry_run, writer, silent_skip=silent_skip, thread_id=thread_id)
        except:
            traceback.print_exc()
            writer(f'Failed to make {rule.name}\n', logkind='error')
        finally:
            set_result_fn(rule, res)

