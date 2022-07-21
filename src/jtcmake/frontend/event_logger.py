from typing import Union
from collections.abc import Mapping, Sequence
import inspect
from ..logwriter.writer import IWriter, RichStr
from ..core import events


def create_event_callback(w: IWriter, rules, base):
    def callback(e):
        if isinstance(e, events.RuleEvent):
            w.info(str(e), e.rule.name)

        if isinstance(e, events.Skip):
            msg = 'Nothing to be done for ' # TODO
            if e.rule in rules:
                w.info(msg)
            else:
                w.debug(msg)
        elif isinstance(e, events.Start):
            ...
        elif isinstance(e, events.Done):
            ...
        elif isinstance(e, events.DryRun):
            ...
        elif isinstance(e, events.StopOnFail):
            ...
        elif isinstance(e, events.UpdateCheckError):
            ...
        elif isinstance(e, events.PreProcError):
            ...
        elif isinstance(e, events.ExecError):
            ...
        elif isinstance(e, events.PostProcError):
            ...
        elif isinstance(e, events.FatalError):
            ...
        else:
            writer.warning(f'Unhandled event: {e}')

    return callback
    

def get_func_name(f):
    try:
        name, mod = f.__qualname__, f.__module__

        if mod == 'builtins':
            name
        else:
            return f'{mod}.{name}'
    except:
        return '<unkonw function>'


def tostrs_func_call(dst: Sequence[Union[str, RichStr]], f, args, kwargs):
    bn = inspect.signature(f).bind(*args, **kwargs)
    bn.apply_defaults()
    
    dst.append(get_func_name(f) + '(\n')

    for k,v in bn:
        dst.append(f'  {k}=')
        tostr_obj(dst, v)
        dst.append(',\n')
    dst.append(')\n')


def tostr_obj(dst: Sequence[Union[str, RichStr]], o):
    if isinstance(o, (tuple, list)):
        dst.append('[')
        for v in o:
            tostr_obj(dst, v)
            dst.append(', ')
        dst.append(']')
    elif isinstance(o, Mapping):
        dst.append('{')
        for k,v in o.items():
            dst.append(repr(k) + ': ')
            tostr_obj(dst, v)
            dst.append(', ')
        dst.append('}')
    elif isinstance(o, Path):
        dst.append(RichStr(repr(o)), link=str(o))
    else:
        dst.append(repr(o))


