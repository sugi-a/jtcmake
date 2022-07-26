from collections.abc import Mapping


class StructKey(tuple):
    def __new__(cls, struct_key):
        return super().__new__(cls, struct_key)

    def __getitem__(self, key):
        if not isinstance(key, (int, str)):
            raise ValueError(f'Key must be int or str. Given {key}')

        return StructKey((*self, key))

    def __getattr__(self, key):
        return self[key]

    def __repr__(self):
        return f'StructKey({super().__repr__()})'


def struct_get(struct, struct_key):
    for k in struct_key:
        struct = struct[k]

    return struct


def map_structure(
    map_fn, struct,
    seq_factory={list: list, tuple: tuple},
    map_factory={(dict, Mapping): dict}
):
    assert callable(map_fn)

    def rec(struct):
        if isinstance(struct, StructKey):
            return map_fn(struct)

        for src, dst in seq_factory.items():
            if isinstance(struct, src):
                return dst(map(rec, struct))

        for src, dst in map_factory.items():
            if isinstance(struct, src):
                return dst({k: rec(struct[k]) for k in struct.keys()})

        return map_fn(struct)

    return rec(struct)


def ordered_map_structure(
    map_fn, struct,
    seq_factory={list: list, tuple: tuple},
    map_factory={(dict, Mapping): dict}
):
    assert callable(map_fn)

    def rec(struct):
        if isinstance(struct, StructKey):
            return map_fn(struct)

        for src, dst in seq_factory.items():
            if isinstance(struct, src):
                return dst(map(rec, struct))

        for src, dst in map_factory.items():
            if isinstance(struct, src):
                keys = sorted(struct.keys(), key=lambda x: (hash(x), x))
                return dst({k: rec(struct[k]) for k in keys})

        return map_fn(struct)

    return rec(struct)



def flatten(struct):
    res = []

    def rec(node):
        if isinstance(node, StructKey):
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

    rec(struct)
    return res


def flatten_to_struct_keys(struct):
    res = []

    def rec(node, struct_key):
        if isinstance(node, StructKey):
            res.append(struct_key)
        elif isinstance(node, (tuple, list)):
            for i,v in enumerate(node):
                rec(v, (*struct_key, i))
        elif isinstance(node, (dict, Mapping)):
            keys = sorted(node.keys(), key=lambda x: (hash(x), x))
            for k in keys:
                rec(node[k], (*struct_key, k))
        else:
            res.append(struct_key)

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
        res = ordered_map_structure(map_fn, ref_struct)
    except NotEnoughElementError as e:
        err = e

    if err is not None:
        raise err

    if i != len(flatten_seq):
        raise TypeError('too many elements in flatten_seq')

    return res
