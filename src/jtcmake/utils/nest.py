from typing import Any, Callable, Iterable, List, Mapping, Optional, Set, Type, Sequence


def _raise_structure_unmatch(i: int):
    raise TypeError(
        f"Structure of the 0-th nest does not match that of the {i}-th nest"
    )


T_Seq_Factory = Mapping[Type[Sequence[Any]], Callable[[Iterable[Any]], Sequence[Any]]]
T_Map_Factory = Mapping[Type[Mapping[Any, Any]], Callable[[Mapping[Any, Any]], Mapping[Any, Any]]]
T_Set_Factory = Mapping[Type[Set[Any]], Callable[[Iterable[Any]], Set[Any]]]


def map_structure(
    map_fn: Callable[[object], object],
    *nests: object,
    seq_factory: T_Seq_Factory = {list: list, tuple: tuple},
    map_factory: T_Map_Factory = {dict: dict},
):
    assert callable(map_fn)

    def _rec(nests: Sequence[Any]):
        nest0, *rest = nests

        for src, dst in seq_factory.items():
            if isinstance(nest0, src):
                for i, nest in enumerate(rest):
                    if not isinstance(nest, src):
                        _raise_structure_unmatch(i + 1)

                return dst(map(_rec, zip(*nests)))

        for src, dst in map_factory.items():
            if isinstance(nest0, src):
                for i, nest in enumerate(rest):
                    if not isinstance(nest, src):
                        _raise_structure_unmatch(i + 1)

                    if set(nest0) != set(nest):
                        _raise_structure_unmatch(i + 1)

                return dst(
                    {k: _rec(tuple(nest[k] for nest in nests)) for k in nest0}
                )

        return map_fn(*nests)

    return _rec(nests)


def ordered_map_structure(
    map_fn: Callable[[Any], Any],
    nest: object,
    seq_factory: T_Seq_Factory = {list: list, tuple: tuple},
    map_factory: T_Map_Factory = {dict: dict, Mapping: dict},
):
    assert callable(map_fn)

    def rec(nest: object):
        for src, dst in seq_factory.items():
            if isinstance(nest, src):
                return dst(map(rec, nest))

        for src, dst in map_factory.items():
            if isinstance(nest, src):
                keys = sorted(nest.keys(), key=lambda x: (hash(x), x))
                return dst({k: rec(nest[k]) for k in keys})

        return map_fn(nest)

    return rec(nest)


def map_structure_with_set(
    map_fn: Callable[[Any], Any],
    nest: Any,
    seq_factory: T_Seq_Factory = { list: list, tuple: tuple },
    map_factory: T_Map_Factory = { dict: dict },
    set_factory: T_Set_Factory = { set: set },
):
    assert callable(map_fn)

    def rec(nest: Any):
        for src, dst in seq_factory.items():
            if isinstance(nest, src):
                return dst(map(rec, nest))

        for src, dst in map_factory.items():
            if isinstance(nest, src):
                return dst({k: rec(v) for k, v in nest.items()})

        for src, dst in set_factory.items():
            if isinstance(nest, src):
                return dst(map(rec, nest))

        return map_fn(nest)

    return rec(nest)


def flatten(nest: object) -> List[object]:
    res: List[object] = []

    def rec(node: object):
        if isinstance(node, (tuple, list)):
            for v in node:  # pyright: ignore [reportUnknownVariableType]
                rec(v)
        elif isinstance(node, (dict, Mapping)):
            keys: List[object] = sorted(node.keys(), key=lambda x: (hash(x), x))
            for k in keys:
                rec(node[k])
        else:
            res.append(node)

    rec(nest)
    return res


class NotEnoughElementError(Exception):
    def __init__(self, msg: Optional[str] = None):
        super().__init__(msg or "not enough elements in flatten seq")


def pack_sequence_as(ref_struct: object, flatten_seq: List[object]):
    i = 0

    def map_fn(x: object):
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
