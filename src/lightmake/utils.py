import sys, os, pathlib, re
from collections.abc import Mapping

def map_nested(
        nested, map_fn,
        _seq_src_type_dst_factory_pairs=[(tuple, tuple), (list, list)],
        _map_src_type_dst_factory_pairs=[((dict, Mapping), dict)]
        ):
    def rec(nested):
        for src, dst in _seq_src_type_dst_factory_pairs:
            if isinstance(nested, src):
                return dst(map(rec, nested))

        for src, dst in _map_src_type_dst_factory_pairs:
            if isinstance(nested, src):
                return dst({k: rec(v) for k,v in nested.items()})

        return map_fn(nested)

    return rec(nested)
        

def flatten_nested(nested):
    res = []
    def rec(node):
        if isinstance(node, (tuple, list)):
            for v in node:
                rec(v)
        elif isinstance(node, dict):
            for v in node.values():
                rec(v)
        else:
            res.append(node)
    rec(nested)
    return res


def get_deep(nested, keys):
    for k in keys:
        nested = nested[k]

    return nested


def should_update(dsts, srcs):
    if len(dsts) == 0:
        return False

    srcs = list(filter(os.path.exists, srcs))
    latest = 0 if len(srcs) == 0 else max(map(os.path.getmtime, srcs))

    for f in dsts:
        try:
            if os.path.getmtime(f) < latest:
                return True
        except:
            return True

    return False


def isipynb():
    try:
        shell = get_ipython().__class__.__name__
        return shell == 'ZMQInteractiveShell'
    except NameError:
        return False
            
