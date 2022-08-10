import os, sys, re, traceback, inspect, abc, time, enum, queue, pickle
from multiprocessing import get_context
from threading import Thread, Condition, Lock

from collections import defaultdict

from . import events
from .rule import Event, IRule
from .make import process_rule, Result


def _collect_rules(seed_rules):
    """collect rules which seed_rules depend on"""
    rules = set()           # set<Rule>
    b2a = defaultdict(set)  # dict<Rule, Rule> before to after

    def find_deps(r):
        if r in rules:
            return

        rules.add(r)

        for depr in r.deplist:
            find_deps(depr)
            b2a[depr].add(r)

    for r in seed_rules:
        find_deps(r)
    
    return list(rules), b2a
        

def make_mp_spawn(rules, dry_run, keep_going, callback, njobs):
    if len(rules) == 0:
        return

    assert njobs >= 2

    # Use the process starting method 'spawn' regardless of OS
    ctx = get_context('spawn')

    # Gather relevant rules
    main_rules = rules
    rules, b2a = _collect_rules(main_rules)

    dep_cnt = { r: len(r.deplist) for r in rules }

    # Check inter-process transferability
    sendable = _test_interproc_portabability(rules, ctx)
    _log_sendable_stats(sendable)
    sendable = { rules[i]: v for i, v in enumerate(sendable) }

    # state vars
    updated_rules = set()  # rules processed and not skipped

    job_q = []  # FIFO: visit nodes in depth-first order

    nidles = njobs  # #idle slots

    stop = False

    cv = Condition()  # for the above state vars
    cb_lock = Lock()  # used when callback()

    event_q = ctx.Queue()

    # Add rules with no dependencies to the job queue
    for r in rules:
        if dep_cnt[r] == 0:
            job_q.append(r)

    def stop_or_done():
        return stop or (len(job_q) == 0 and nidles == njobs)

    def get_rule():
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

    def set_result(rule, res):
        nonlocal stop, nidles

        with cv:
            nidles += 1
            assert nidles <= njobs

            if res is None:  # fatal error
                stop = True
            elif res == Result.Fail:
                if not keep_going:
                    stop = True
            else:
                if res == Result.Update:
                    updated_rules.add(rule)

                for nxt in b2a[rule]:
                    dep_cnt[nxt] -= 1
                    assert dep_cnt[nxt] >= 0

                    if dep_cnt[nxt] == 0:
                        job_q.append(nxt)

            cv.notify_all()

    def callback_(*args, **kwargs):
        with cb_lock:
            callback(*args, **kwargs)
                

    def event_q_handler():
        while True:
            if stop_or_done():
                return

            try:
                event_q.get(True, 1)
            except queue.Empty as e:
                pass
        

    args = (
        ctx, get_rule, set_result,
        event_q,
        main_rules, sendable, dry_run, callback_
    )

    threads = [Thread(target=worker, args=(*args, i)) for i in range(njobs)]

    for t in threads:
        t.start()

    thread_event_q_handler = Thread(target=event_q_handler)
    thread_event_q_handler.start()

    try:
        for t in threads:
            t.join()

        #thread_event_q_handler.join()
    except:
        with cv:
            stop = True
            cv.notify_all()


def worker(
    ctx, get_rule, set_result,
    event_q,  # for process only
    main_rules, sendable, dry_run, callback,
    name,
):
    name = f'worker{name}'
    with ctx.Pool(1, _init_event_q, (event_q,)) as pool:
        while True:
            rule = get_rule()

            if rule is None:
                return

            res = None

            try:
                t = time.time()
                if sendable[rule]:
                    res = pool.apply(process_worker, (rule, dry_run))
                else:
                    res = process_rule(rule, dry_run, set(), set(), callback)
                print('elapsed', time.time() - t)
            except (Exception, KeyboardInterrupt) as e:
                traceback.print_exc()
                try:
                    callback(events.FatalError(rule, e))
                except:
                    pass
            finally:
                set_result(rule, res)

                if res is None:
                    return


_event_q = None  # used by worker Processes

def _init_event_q(q):
    global _event_q
    assert _event_q is None
    _event_q = q


def process_worker(rule, dry_run):
    def cb(e):
        _event_q.put(e)

    return process_rule(rule, dry_run, set(), set(), cb)


def _test_interproc_portabability(objs, ctx):
    n = len(objs)
    picklable = [True] * n

    codes = [None] * n

    sys.stderr.write('Checking picklability\n')

    for i in range(n):
        try:
            codes[i] = pickle.dumps(objs[i])
        except:
            picklable[i] = False

    sys.stderr.write('Checking inter-process portability\n')

    par, child = ctx.Pipe()

    p = ctx.Process(target=_test_unpicklable, args=(codes, child))
    p.start()

    unpicklable = par.recv()

    p.join()

    return [a and b for a, b in zip(picklable, unpicklable)]


def _test_unpicklable(codes, conn):
    res = [True] * len(codes)

    for i,c in enumerate(codes):
        try:
            pickle.loads(c)
        except:
            res[i] = False
    
    conn.send(res)
    


def _log_sendable_stats(sendables):
    n = len(sendables)
    ok = sum(1 for x in sendables if x)
    ng = n - ok

    sys.stderr.write(
        f'{ng} out of {n} Rules will be executed in the main process '
        'since they cannot be transfered to a child process\n'
    )

