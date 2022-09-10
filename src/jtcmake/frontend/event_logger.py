from collections.abc import Mapping, Sequence
import os, inspect, warnings
from pathlib import Path

from ..logwriter.writer import IWriter, RichStr
from ..core import events


def log_make_event(w, e):
    if isinstance(e, events.ErrorRuleEvent):
        r = e.rule

        # Show stack trace and error message
        w.warning("".join(e.trace_exc.format()))

        if r.name is not None:
            name = "/".join(r.name)
        else:
            name = "<unknown>"
            warnings.warn(
                f"Internal Error: an event of unnamed Rule has been emitted.\n"
            )

        name = RichStr(name, c=(0, 0xCC, 0))

        if isinstance(e, events.UpdateCheckError):
            w.error(
                f"Failed to make ",
                name,
                ": An error occured while checking if update is necessary\n",
            )
        elif isinstance(e, events.PreProcError):
            w.error(
                f"Failed to make ",
                name,
                f": An error occured during preprocessing\n",
            )
        elif isinstance(e, events.ExecError):
            w.error(f"Failed to make ", name, f": Method failed\n")
        elif isinstance(e, events.PostProcError):
            w.error(
                f"Failed to make {name}: "
                f"An error occured during post-processing. "
                f"Make sure to remove the output files (if any) "
                f"by yourself\n"
            )
        elif isinstance(e, events.FatalError):
            w.error("Fatal error\n")
        else:
            w.warning(f"Unhandled error event for {r}\n")

        return
    elif isinstance(e, events.RuleEvent):
        r = e.rule

        if r.name is not None:
            name = "/".join(r.name)
        else:
            name = "<unknown>"
            warnings.warn(
                f"Internal Error: an event of unnamed Rule has been emitted.\n"
            )

        name = RichStr(name, c=(0, 0xCC, 0))

        if isinstance(e, events.Skip):
            if e.is_direct_target:
                w.info("Skip ", name, "\n")
            else:
                w.debug("Skip ", name, "\n")
        elif isinstance(e, events.Start):
            msg = []
            tostrs_func_call(msg, r.method, r.args, r.kwargs)
            msg = add_indent(msg, "  ")
            w.info("Make ", name, "\n", *msg)
        elif isinstance(e, events.Done):
            w.info(f"Done ", name, "\n")
        elif isinstance(e, events.DryRun):
            msg = []
            tostrs_func_call(msg, r.method, r.args, r.kwargs)
            msg = add_indent(msg, "  ")
            w.info("Make (dry) ", name, "\n", *msg)
        else:
            w.warning(f"Unhandled event for {r}\n")
        return
    elif isinstance(e, events.StopOnFail):
        w.warning(f"Execution aborted due to an error\n")
    else:
        w.warning(f"Unhandled event {e}\n")


def add_indent(sl, indent):
    res = []
    for i, s in enumerate(sl):
        if i == 0 or (i > 0 and len(sl[i - 1]) > 0 and sl[i - 1][-1] == "\n"):
            res.append(indent + s)
        else:
            res.append(s)
    return res


def get_func_name(f):
    try:
        name, mod = f.__qualname__, f.__module__

        if mod == "builtins" or mod == "__main__":
            return name
        else:
            return f"{mod}.{name}"
    except:
        return "<unkonw function>"


def tostrs_func_call(dst, f, args, kwargs):
    bn = inspect.signature(f).bind(*args, **kwargs)
    bn.apply_defaults()

    dst.append(RichStr(get_func_name(f), c=(0, 0x80, 0xFF)))
    dst.append("(\n")

    for k, v in bn.arguments.items():
        dst.append(RichStr(f"  {k}", c=(0xFF, 0x80, 0)))
        dst.append(f" = ")
        tostrs_obj(dst, v, capacity=500)
        dst.append(",\n")
    dst.append(")\n")


def tostrs_obj(dst, o, capacity=None):
    _tostrs_obj(dst, o, capacity or 10**10)


def _tostrs_obj(dst, o, capacity):
    if isinstance(o, (tuple, list)):
        dst.append("[")
        for i, v in enumerate(o):
            if capacity <= 0:
                dst.append(", ...")
                capacity -= 5
                break
            capacity = _tostrs_obj(dst, v, capacity)
            if i < len(o) - 1:
                dst.append(", ")
                capacity -= 2
        dst.append("]")
        return capacity
    elif isinstance(o, Mapping):
        dst.append("{")
        for i, (k, v) in enumerate(o.items()):
            if capacity <= 0:
                dst.append(", ... ")
                capacity -= 5
                break
            dst.append(repr(k) + ": ")
            capacity = _tostrs_obj(dst, v, capacity)
            if i < len(o) - 1:
                dst.append(", ")
                capacity -= 2
        dst.append("}")
        return capacity
    elif isinstance(o, Path):
        res = RichStr(repr(o), link=str(o))
        dst.append(res)
        return capacity - len(res)
    else:
        res = repr(o)
        if len(res) > capacity:
            res = res[: capacity // 2] + " ... " + res[-capacity // 2 :]
        dst.append(res)
        return capacity - len(res)
