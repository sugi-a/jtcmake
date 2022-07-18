from __future__ import annotations
from typing import Union, Sequence
from collections.abc import Mapping


class DeepKey(tuple):
    def __new__(cls, deepkey: Sequence[Union[int, str]]):
        return super().__new__(cls, deepkey)

    def __getitem__(self, key: Union[int, str]) -> DeepKey:
        if not isinstance(key, (int, str)):
            raise ValueError(f'Key must be int or str. Given {key}')

        return DeepKey((*self, key))

    def __getattr__(self, key: str) -> DeepKey:
        return self[key] 

    def __repr__(self) -> str:
        return f'DeepKey({super().__repr__()})'


def deep_get(struct, deepkey):
    for k in deepkey:
        struct = struct[k]

    return struct


def map_structure(
    map_fn, struct,
    seq_factory={list: list, tuple: tuple},
    map_factory={(dict, Mapping): dict}
):
    assert callable(map_fn)
    def rec(struct):
        if isinstance(struct, DeepKey):
            return map_fn(struct)

        for src, dst in seq_factory.items():
            if isinstance(struct, src):
                return dst(map(rec, struct))

        for src, dst in map_factory.items():
            if isinstance(struct, src):
                return dst({k: rec(struct[k]) for k in struct.keys()})

        return map_fn(struct)

    return rec(struct)


def flatten(struct):
    res = []
    def rec(node):
        if isinstance(node, DeepKey):
            res.append(node)
        elif isinstance(node, (tuple, list)):
            for v in node: rec(v)
        elif isinstance(node, (dict, Mapping)):
            keys = sorted(node.keys())
            for k in keys: rec(node[k])
        else:
            res.append(node)

    rec(struct)
    return res


def flatten_to_deepkeys(struct):
    res = []
    def rec(node, deepkey):
        if isinstance(node, DeepKey):
            res.append(deepkey)
        elif isinstance(node, (tuple, list)):
            for i,v in enumerate(node): rec(v, (*deepkey, i))
        elif isinstance(node, (dict, Mapping)):
            keys = sorted(node.keys())
            for k in keys: rec(node[k], (*deepkey, k))
        else:
            res.append(deepkey)

    rec(struct, ())
    return res


class NotEnoughElementError(Exception):
    def __init__(self, msg=None):
        super().__init__(msg or 'not enough elements in flatten seq')


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
        res = map_structure(map_fn, ref_struct)
    except NotEnoughElementError as e:
        err = e

    if err is not None:
        raise err

    if i != len(flatten_seq):
        raise TypeError('too many elements in flatten_seq')

    return res


