from typing import Union
from collections.abc import Mapping, Sequence
import os, inspect
from pathlib import Path

from ..logwriter.writer import IWriter, RichStr
from ..core import events


def create_event_callback(w: IWriter, rules, base):
    def callback(e):
        if isinstance(e, events.ErrorRuleEvent):
            r = e.rule
            err = e.err

            if isinstance(e, events.UpdateCheckError):
                w.error(
                    f'Failed to make {r.name}: '
                    f'An error occured while checking if update is necessary: '
                    f'{err}'
                )
            elif isinstance(e, events.PreProcError):
                w.error(
                    f'Failed to make {r.name}: '
                    f'An error occured during preprocessing: {err}'
                )
            elif isinstance(e, events.ExecError):
                w.error(
                    f'Failed to make {r.name}: Method failed: {err}'
                )
            elif isinstance(e, events.PostProcError):
                w.error(
                    f'Failed to make {r.name}: '
                    f'An error occured during post-processing: {err}. '
                    f'Make sure to remove the output files (if any) '
                    f'by yourself'
                )
            elif isinstance(e, events.FatalError):
                w.error('Fatal error')
            else:
                w.warning(f'Unhandled error event for {r}: {err}')
            return
        elif isinstance(e, events.RuleEvent):
            r = e.rule
            if isinstance(e, events.Skip):
                msg = f'Skip {r.name}'
                if e.rule in rules:
                    w.info(msg)
                else:
                    w.debug(msg)
            elif isinstance(e, events.Start):
                msg = []
                tostrs_func_call(msg, r.method, r.args, r.kwargs)
                msg = replace_base(msg, base)
                msg = add_indent(msg, '  ')
                msg.insert(0, f'Make {r.name}\n')
                w.info(*msg)
            elif isinstance(e, events.Done):
                w.info(f'Done {r.name}')
            elif isinstance(e, events.DryRun):
                msg = []
                tostrs_func_call(msg, r.method, r.args, r.kwargs)
                msg = replace_base(msg, base)
                msg = add_indent(msg, '  ')
                msg.insert(0, f'Make (dry) {r.name}\n')
                w.info(*msg)
            else:
                w.warning(f'Unhandled event for {r}')
            return
        elif isinstance(e, events.StopOnFail):
            w.warning(f'Execution aborted due to an error')

    return callback


def replace_base(sl, base):
    res = []
    for s in sl:
        if isinstance(s, RichStr) and s.link is not None:
            res.append(RichStr(s, link=os.path.relpath(s.link, base)))
        else:
            res.append(s)
    return res


def add_indent(sl, indent):
    res = []
    for i,s in enumerate(sl):
        if i == 0 or (i > 0 and len(sl[i - 1]) > 0 and sl[i - 1][-1] == '\n'):
            res.append(indent + s)
        else:
            res.append(s)
    return res


def get_func_name(f):
    try:
        name, mod = f.__qualname__, f.__module__

        if mod == 'builtins' or mod == '__main__':
            return name
        else:
            return f'{mod}.{name}'
    except:
        return '<unkonw function>'


def tostrs_func_call(dst: Sequence[Union[str, RichStr]], f, args, kwargs):
    bn = inspect.signature(f).bind(*args, **kwargs)
    bn.apply_defaults()
    
    dst.append(get_func_name(f) + '(\n')

    for k,v in bn.arguments.items():
        dst.append(f'  {k}=')
        tostrs_obj(dst, v, capacity=500)
        dst.append(',\n')
    dst.append(')\n')


def tostrs_obj(dst: Sequence[Union[str, RichStr]], o, capacity=None):
    _tostrs_obj(dst, o, capacity or 10 ** 10)


def _tostrs_obj(dst: Sequence[Union[str, RichStr]], o, capacity):
    if isinstance(o, (tuple, list)):
        dst.append('[')
        for i,v in enumerate(o):
            if capacity <= 0:
                dst.append(', ...')
                break
            capacity = _tostrs_obj(dst, v, capacity)
            if i < len(o) - 1:
                dst.append(', ')
        dst.append(']')
    elif isinstance(o, Mapping):
        dst.append('{')
        for i,(k,v) in enumerate(o.items()):
            if capacity <= 0:
                dst.append(', ... ')
                break
            dst.append(repr(k) + ': ')
            capacity = _tostrs_obj(dst, v, capacity)
            if i < len(o) - 1:
                dst.append(', ')
        dst.append('}')
    elif isinstance(o, Path):
        res = RichStr(repr(o), link=str(o))
        dst.append(res)
        return capacity - len(res)
    else:
        res = repr(o)
        if len(res) > capacity:
            res = res[: capacity // 2] + ' ... ' + res[-capacity//2:]
        dst.append(res)
        return capacity - len(res)


