from typing import Any, Callable
from collections.abc import Mapping


class NestKey(tuple):
    def __new__(cls, nest_key):
        return super().__new__(cls, nest_key)

    def __getitem__(self, key):
        if not isinstance(key, (int, str)):
            raise ValueError(f"Key must be int or str. Given {key}")

        return NestKey((*self, key))

    def __getattr__(self, key):
        return self[key]

    def __repr__(self):
        return f"NestKey({super().__repr__()})"


def nest_get(nest: Any, nest_key: NestKey):
    for k in nest_key:
        nest = nest[k]

    return nest


def _raise_structure_unmatch(i: int):
    raise TypeError(
        f"Structure of the 0-th nest does not match that of the {i}-th nest"
    )


def map_structure(
    map_fn: Callable,
    *nests,
    seq_factory={list: list, tuple: tuple},
    map_factory={dict: dict},
):
    assert callable(map_fn)

    containert = (*seq_factory, *map_factory)

    def _rec(nests):
        nest0, *rest = nests

        if isinstance(nest0, NestKey):
            for i, nest in enumerate(rest):
                if not isinstance(nest, NestKey) and isinstance(
                    nest, containert
                ):
                    _raise_structure_unmatch(i + 1)
            return map_fn(*nests)

        for src, dst in seq_factory.items():
            if isinstance(nest0, src):
                for i, nest in enumerate(rest):
                    if isinstance(nest, NestKey) or not isinstance(nest, src):
                        _raise_structure_unmatch(i + 1)

                return dst(map(_rec, zip(*nests)))

        for src, dst in map_factory.items():
            if isinstance(nest0, src):
                for i, nest in enumerate(rest):
                    if isinstance(nest, NestKey) or not isinstance(nest, src):
                        _raise_structure_unmatch(i + 1)

                    if set(nest0) != set(nest):
                        _raise_structure_unmatch(i + 1)

                return dst(
                    {k: _rec(tuple(nest[k] for nest in nests)) for k in nest0}
                )

        return map_fn(*nests)

    return _rec(nests)


def ordered_map_structure(
    map_fn: Callable,
    nest,
    seq_factory={list: list, tuple: tuple},
    map_factory={(dict, Mapping): dict},
):
    assert callable(map_fn)

    def rec(nest):
        if isinstance(nest, NestKey):
            return map_fn(nest)

        for src, dst in seq_factory.items():
            if isinstance(nest, src):
                return dst(map(rec, nest))

        for src, dst in map_factory.items():
            if isinstance(nest, src):
                keys = sorted(nest.keys(), key=lambda x: (hash(x), x))
                return dst({k: rec(nest[k]) for k in keys})

        return map_fn(nest)

    return rec(nest)


def flatten(nest):
    res = []

    def rec(node):
        if isinstance(node, NestKey):
            res.append(node)
        elif isinstance(node, (tuple, list)):
            for v in node:
                rec(v)
        elif isinstance(node, (dict, Mapping)):
            keys = sorted(node.keys(), key=lambda x: (hash(x), x))
            for k in keys:
                rec(node[k])
        else:
            res.append(node)

    rec(nest)
    return res


def flatten_to_nest_keys(nest):
    res = []

    def rec(node, nest_key):
        if isinstance(node, NestKey):
            res.append(nest_key)
        elif isinstance(node, (tuple, list)):
            for i, v in enumerate(node):
                rec(v, (*nest_key, i))
        elif isinstance(node, (dict, Mapping)):
            keys = sorted(node.keys(), key=lambda x: (hash(x), x))
            for k in keys:
                rec(node[k], (*nest_key, k))
        else:
            res.append(nest_key)

    rec(nest, ())
    return res


class NotEnoughElementError(Exception):
    def __init__(self, msg=None):
        super().__init__(msg or "not enough elements in flatten seq")


def pack_sequence_as(ref_struct, flatten_seq):
    i = 0

    def map_fn(x):
        nonlocal i
        i += 1
        if i > len(flatten_seq):
            raise NotEnoughElementError()
        return flatten_seq[i - 1]

    res, err = None, None

    try:
        res = ordered_map_structure(map_fn, ref_struct)
    except NotEnoughElementError as e:
        err = e

    if err is not None:
        raise err

    if i != len(flatten_seq):
        raise TypeError("too many elements in flatten_seq")

    return res
