from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    Set,
    Type,
    Sequence,
)


T_Seq_Factory = Mapping[
    Type[Sequence[Any]], Callable[[Iterable[Any]], Sequence[Any]]
]
T_Map_Factory = Mapping[
    Type[Mapping[Any, Any]], Callable[[Mapping[Any, Any]], Mapping[Any, Any]]
]
T_Set_Factory = Mapping[Type[Set[Any]], Callable[[Iterable[Any]], Set[Any]]]


def map_structure(
    map_fn: Callable[[object], object],
    nest: Any,
    seq_factory: T_Seq_Factory = {list: list, tuple: tuple},
    map_factory: T_Map_Factory = {dict: dict},
    set_factory: T_Set_Factory = {set: set},
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


def ordered_map_structure(
    map_fn: Callable[[object], object],
    nest: object,
    seq_factory: T_Seq_Factory = {list: list, tuple: tuple},
    map_factory: T_Map_Factory = {dict: dict},
    set_factory: T_Set_Factory = {set: set},
):
    def rec(nest: object):
        for src, dst in seq_factory.items():
            if isinstance(nest, src):
                return dst(map(rec, nest))

        for src, dst in map_factory.items():
            if isinstance(nest, src):
                keys = sorted(nest.keys())
                return dst({k: rec(nest[k]) for k in keys})

        for src, dst in set_factory.items():
            if isinstance(nest, src):
                values = sorted(nest)
                return dst(map(rec, values))

        return map_fn(nest)

    return rec(nest)
