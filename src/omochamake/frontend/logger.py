import sys, os, re
from ..core import Events


def create_event_handler(writer, rule_set):
    def event_handler(e):
        print(e)

        assert isinstance(e, Events.EventBase)
        r = e.rule()

        link_map = r.opaths | r.ipaths
        link_map = {repr(v): v for v in link_map if not os.path.isabs(v)}

        log = lambda t: writer(t, link_map, 'log')
        info = lambda t: writer(t, link_map, 'info')
        warning = lambda t: writer(t, link_map, 'warning')
        error = lambda t: writer(t, link_map, 'error')
        success = lambda t: writer(t, link_map, 'success')

        if isinstance(e, Events.ErrorEventBase):
            err = e.err()
            if isinstance(e, Events.UpdateCheckError):
                error(f'Failed to check update for {r.name}: {err}\n')
            elif isinstance(e, Events.MkdirError):
                warning(f'Failed to mkdir for {r.name}: {err}\n')
            elif isinstance(e, Events.ExecError):
                error(
                    f'Failed to make {r.name}: '
                    f'method {repr_method(r.method)} failed: '
                    f'{err}\n'
                )
            elif isinstance(e, Events.FatalError):
                error(f'Fatal error: {err}\n')
            elif isinstance(e, Events.PostProcError):
                error(f'Failed to post process {r.name}: {err}\n')
            else:
                raise Exception('Unreachable')
        else:
            if isinstance(e, Events.Skip):
                if r in rule_set:
                    log('Nothing to be done for {r.name}')
            elif isinstance(e, Events.Start):
                info(
                    f'{r.name}\n  {repr_method(r.method)}\n' +
                    repr_multi_args(r.args, idt='    ') + 
                    repr_multi_kwargs(r.kwargs, idt='    ')
                )
            elif isinstance(e, Events.Done):
                success('Done {r.name}\n')
            elif isinstance(e, Events.DryRun):
                info(
                    f'{r.name} (dry-run)\n  {repr_method(r.method)}\n' +
                    repr_multi_args(r.args, idt='    ') + 
                    repr_multi_kwargs(r.kwargs, idt='    ')
                )
            elif isinstance(e, Events.StopOnFail):
                error('Terminated')
            elif isinstance(e, Events.SkipReadonly):
                pass

    return event_handler


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

