import os, sys, re, traceback, inspect, abc, time, enum, queue, pickle
from multiprocessing import get_context
from threading import Thread, Condition, Lock

from collections import defaultdict

from . import events
from .rule import Event, IRule
from .make import process_rule, Result


def _collect_rules(id2rule, seed_ids):
    """collect rules on which seed rules depend"""
    ids = set()           # set<ID>
    b2a = defaultdict(set)  # dict<ID, ID> before to after

    def find_deps(i):
        if i in ids:
            return

        ids.add(i)

        for dep in id2rule[i].deplist:
            find_deps(dep)
            b2a[dep].add(i)

    for i in seed_ids:
        find_deps(i)
    
    return list(ids), b2a
        

def make_mp_spawn(id2rule, ids, dry_run, keep_going, callback, njobs):
    if len(ids) == 0:
        return

    assert njobs >= 2

    # Use the process starting method 'spawn' regardless of OS
    ctx = get_context('spawn')

    # Not very confident but this useless Pool seems necessary for later
    # use of Pool in threads to work reliably.
    with ctx.Pool(1):
        pass

    # Gather relevant rules
    main_ids = ids
    ids, b2a = _collect_rules(id2rule, main_ids)

    dep_cnt = { i: len(id2rule[i].deplist) for i in ids }

    # Check inter-process transferability
    rules = [id2rule[i] for i in ids]
    sendable = _test_interproc_portabability(rules, ctx)
    _log_sendable_stats(sendable)
    sendable = { ids[j]: sendable[j] for j in range(len(ids)) }

    # state vars
    updated_ids = set()  # rules processed and not skipped

    job_q = []  # FIFO: visit nodes in depth-first order

    nidles = njobs  # #idle slots

    stop = False

    cv = Condition()  # for the above state vars
    cb_lock = Lock()  # used when callback()

    event_q = ctx.Queue()

    # Add rules with no dependencies to the job queue
    for i in ids:
        if dep_cnt[i] == 0:
            job_q.append(i)

    def stop_or_done():
        return stop or (len(job_q) == 0 and nidles == njobs)

    def get_job():
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

    def set_result(i, res):
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
                    updated_ids.add(i)

                for nxt in b2a[i]:
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
                callback_(event_q.get(True, 1))
            except queue.Empty as e:
                pass
            except Exception:
                traceback.print_exc()
        

    args = (
        ctx,
        get_job,
        set_result,
        event_q,
        id2rule,
        updated_ids,
        main_ids,
        sendable,
        dry_run,
        callback_
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
    ctx,
    get_job,
    set_result,
    event_q,  # for process only
    id2rule,
    updated_ids,
    main_ids,
    sendable,
    dry_run,
    callback,
    name,
):
    name = f'worker{name}'
    with ctx.Pool(1, _init_event_q, (event_q,)) as pool:
        while True:
            i = get_job()

            if i is None:
                return

            rule = id2rule[i]

            res = None

            try:
                par_updated = any(dep in updated_ids for dep in rule.deplist)
                args = (rule, dry_run, par_updated, i in main_ids)

                if sendable[i]:
                    res = pool.apply(process_worker, args)
                else:
                    res = process_rule(*args, callback)
            except (Exception, KeyboardInterrupt) as e:
                traceback.print_exc()
                callback(events.FatalError(rule, e))
            finally:
                set_result(i, res)

                if res is None:
                    return


_event_q = None  # used by worker Processes

def _init_event_q(q):
    global _event_q
    assert _event_q is None
    _event_q = q


def process_worker(rule, dry_run, par_updated, is_main):
    def cb(e):
        _event_q.put(e)

    return process_rule(rule, dry_run, par_updated, is_main, cb)


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

