import sys, os, re, traceback, inspect

from .decls import NOP
from ..utils import should_update

def make(rules, dry_run, stop_on_fail, writer):
    if len(rules) == 0:
        return

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
            result = process_rule(t, dry_run, writer, silent_skip=t not in rules)
        except Exception as e:
            traceback.print_exc()
            msg = f'Failed to make {t.name}\n'
            writer(msg, logkind='error')
            result = False

        if not result and stop_on_fail:
            writer(f'Stop\n')
            return
        

def process_rule(rule, dry_run, writer, silent_skip=False, thread_id=None):
    if thread_id is not None:
        th_sfx = f'(THREAD {thread_id}) '
    else:
        th_sfx = ''

    if rule.method is NOP:
        writer(th_sfx + f'Readonly rule {rule.name}\n', logkind='log')
        return True

    method_name = repr_method(rule.method)

    # for HTML-style log
    link_map = rule.self_path_set | rule.dep_path_set
    link_map = {repr(v): v for v in link_map if not os.path.isabs(v)}

    if dry_run:
        msg = f'{rule.name} (dry-run)\n' + \
            f'  {method_name}\n' + \
            repr_multi_args(rule.args, idt='    ') + \
            repr_multi_kwargs(rule.kwargs, idt='    ')
        writer(th_sfx + msg, link_map=link_map)

        return True
    for dep_path in rule.dep_path_set:
        if not os.path.exists(dep_path):
            msg = f'Failed to make {rule.name}: Cannot find requirement {dep_path}\n'
            writer(th_sfx + msg, logkind='error')

            return False

    if not should_update(list(rule.self_path_set), list(rule.dep_path_set)):
        if not silent_skip:
            writer(th_sfx + f'Nothing to be done for {rule.name}\n', logkind='log')
        return True

    msg = f'{rule.name}\n  {method_name}\n' + \
        repr_multi_args(rule.args, idt='    ') + \
        repr_multi_kwargs(rule.kwargs, idt='    ')
    writer(th_sfx + msg, link_map=link_map)

    for p in rule.self_path_set:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
        except:
            writer(th_sfx + 'WARNING: Failed to mkdir for {p}\n', logkind='warning')

    try:
        rule.method(*rule.args, **rule.kwargs)
    except:
        traceback.print_exc()
        msg = f'Failed to make {rule.name}: method {method_name} failed\n'
        writer(th_sfx + msg, logkind='error')

        return False

    writer(th_sfx + f'Done {rule.name}\n', logkind='success')

    return True

def repr_method(method):
    try:
        name = method.__qualname__
        mod = method.__module__
        sig = str(inspect.signature(method))

        if mod == 'builtins':
            return f'{name}{sig}'
        else:
            return f'{mod}.{name}{sig}'
    except:
        return '<unknown>'


def repr_multi_args(args, truncn=10, idt='  '):
    _repr = lambda v: repr_var_trunc(v, 500)

    if len(args) == 0:
        return ''

    if len(args) > truncn:
        n = truncn // 2
        a = idt + f',\n{idt}'.join(map(_repr, args[:n])) + '\n'
        b = idt + f',\n{idt}'.join(map(_repr, args[-n:])) + '\n'
        return a + idt + '...\n' + b
    else:
        return idt + f',\n{idt}'.join(map(_repr, args)) + '\n'


def repr_multi_kwargs(kwargs, truncn=10, idt='  '):
    _repr = lambda kv: repr_var_trunc(kv[0], 500) + '=' + repr_var_trunc(kv[1], 500)

    if len(kwargs) == 0:
        return ''

    if len(kwargs) > truncn:
        n = truncn // 2
        items = list(kwargs.items())
        a = idt + ',\n{idt}'.join(map(_repr, items[:n])) + '\n'
        b = idt + ',\n{idt}'.join(map(_repr, items[-n:])) + '\n'
        return a + idt + '...\n' + b
    else:
        return idt + f',\n{idt}'.join(map(_repr, kwargs.items())) + '\n'


def repr_var_trunc(v, maxlen):
    s = repr(v)
    if len(s) > maxlen:
        n = maxlen // 2 - 2
        s = s[:n] + ' ... ' + s[-n:]
    return s

