from __future__ import annotations
import os
from hashlib import sha256
from numbers import Complex
from typing import Callable, Mapping, Optional, Sequence, Set, List

from .abc import IMemoWrapper, IMemo

MAX_RAW_REPRESENTATION_LEN = 1000

class StrHashMemo(IMemoWrapper):
    __slots__ = ("text")
    text: str

    def __init__(self, text: str):
        if len(text) > MAX_RAW_REPRESENTATION_LEN:
            self.text = _hash_fn(text)
        else:
            self.text = text

    def compare(self, other: IMemo) -> bool:
        if isinstance(other, StrHashMemo):
            return self.text == other.text
        else:
            return False

    def to_str(self) -> str:
        return self.text

    @classmethod
    def from_str(cls, s: str) -> StrHashMemo:
        return cls(s)

    @classmethod
    def create(cls, args: object) -> StrHashMemo:
        return cls(stringify(args, None))
    

def _hash_fn(s: str):
    return sha256(s.encode("utf8")).digest().hex()


SUPPORTED_ATOM_TYPES = (  # pyright: ignore [reportUnknownVariableType]
    str,
    type(None),
    Complex,
    bool,
    bytes,
    bytearray,
    os.PathLike
)


def stringify(
    nest: object,
    default: Optional[Callable[[object], object]]
) -> str:
    def _default(_: object):
        raise TypeError()

    dst: List[str] = []
    _stringify(nest, dst, set(), default or _default)

    return "".join(dst)


def _stringify(
    nest: object,
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object]
) -> None:
    if isinstance(nest, (tuple, list)):
        stringify_sequence(nest, dst, visited_container, default)
    elif isinstance(nest, set):
        stringify_set(nest, dst, visited_container, default)
    elif isinstance(nest, dict):
        stringify_mapping(nest, dst, visited_container, default)
    else:
        stringify_atom(nest, dst, visited_container, default)


def _check_and_update_visited(nest: object, visited_container: Set[int]):
    i = id(nest)
    if i in visited_container:
        raise Exception("Cannot serialize cyclic structure")
    visited_container.add(i)


def stringify_sequence(
    nest: Sequence[object],
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object]
):
    _check_and_update_visited(nest, visited_container)

    dst.append("(" if isinstance(nest, tuple) else "[")
    for v in nest:
        _stringify(v, dst, visited_container, default)
        dst.append(",")
    dst.append(")" if isinstance(nest, tuple) else "]")


def stringify_mapping(
    nest: Mapping[object, object],
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object]
):
    _check_and_update_visited(nest, visited_container)

    try:
        keys: List[object] = sorted(nest, key=lambda x: (hash(x), x))
    except TypeError as e:
        e_ = TypeError("dict in memoization values must have sortable keys")
        raise e_ from e

    dst.append("{")

    for k in keys:  # pyright: ignore [reportUnknownVariableType]
        _stringify(k, dst, visited_container, default)
        dst.append(":")
        _stringify(nest[k], dst, visited_container, default)
        dst.append(",")
    dst.append("}")


def stringify_set(
    nest: Set[object],
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object]
):
    _check_and_update_visited(nest, visited_container)

    try:
        ordered: List[object] = sorted(nest, key=lambda x: (hash(x), x))
    except TypeError as e:
        e_ = TypeError("set in memoization values must have sortable values")
        raise e_ from e

    dst.append("{")

    for v in ordered:
        _stringify(v, dst, visited_container, default)
        dst.append(",")

    dst.append(")")


def stringify_atom(
    atom: object,
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object]
):
    """
    atom must not be a container (list/tuple/dict/set)
    """
    if atom is None:
        dst.append("None")
    elif isinstance(atom, str):
        dst.append(repr(atom))
    elif isinstance(atom, Complex):
        dst.append(repr(atom))
    elif isinstance(atom, bool):
        dst.append(repr(atom))
    elif isinstance(atom, bytes):
        dst.append(repr(atom))
    elif isinstance(atom, bytearray):
        dst.append(repr(atom))
    elif isinstance(atom, os.PathLike):
        dst.append(f"PathLike({repr(os.fspath(atom))})")
    else:
        try:
            v = default(atom)
        except TypeError:
            raise TypeError(f"{atom} is not serializable")

        _stringify(v, dst, visited_container, default)
