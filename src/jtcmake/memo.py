from __future__ import annotations
import os
import json
from pathlib import Path
from hashlib import sha256
from abc import ABCMeta
from numbers import Complex
from typing import (
    Callable,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    List,
    TypeVar,
    Generic,
)

from .raw_rule import IMemo


ENCODING = "utf8"

_T_Memo = TypeVar("_T_Memo")


class Memo(IMemo, Generic[_T_Memo], metaclass=ABCMeta):
    def __init__(
        self,
        args: object,
        lazy_args_gen: Callable[[], object],
        memo_file: str | os.PathLike[str],
        normalizer: Callable[[object], _T_Memo],
        serializer: Callable[[_T_Memo], str],
        deserializer: Callable[[str], _T_Memo],
        extra_info: str = "",
    ) -> None:
        self.memo_file = Path(memo_file)
        self.normalizer = normalizer
        self.serializer = serializer
        self.deserializer = deserializer

        self.extra_info = extra_info

        self.args = normalizer(args)
        self.lazy_args_gen = lazy_args_gen
        self._lazy_args = None

    @property
    def lazy_args(self) -> _T_Memo:
        if self._lazy_args is None:
            self._lazy_args = self.normalizer(self.lazy_args_gen())

        return self._lazy_args

    def compare(self) -> bool:
        return self.load_memo() == (self.args, self.lazy_args)

    def update(self):
        self.store_memo()

    def load_memo(self) -> None | tuple[object, object]:
        try:
            with open(self.memo_file) as f:
                obj: dict[str, object] = json.load(f)
        except Exception:
            return None

        if not isinstance(
            obj, dict
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            return None

        args, lazy_args = obj.get("args"), obj.get("lazy_args")

        if not isinstance(args, str) or not isinstance(lazy_args, str):
            return None

        return self.deserializer(args), self.deserializer(lazy_args)

    def store_memo(self):
        saved_obj = {
            "args": self.serializer(self.args),
            "lazy_args": self.serializer(self.lazy_args),
            "extra_info": self.extra_info,
        }

        os.makedirs(self.memo_file.parent, exist_ok=True)
        with open(self.memo_file, "w") as f:
            json.dump(saved_obj, f)


MAX_RAW_REPRESENTATION_LEN = 1000


def string_normalizer(args: object) -> str:
    s = stringify(args, None)
    if len(s) > MAX_RAW_REPRESENTATION_LEN:
        return _hash_fn(s)
    else:
        return s


def string_serializer(s: str) -> str:
    return s


def string_deserializer(s: str) -> str:
    return s


def _hash_fn(s: str):
    return sha256(s.encode("utf8")).digest().hex()


SUPPORTED_ATOM_TYPES = (  # pyright: ignore [reportUnknownVariableType]
    str,
    type(None),
    Complex,
    bool,
    bytes,
    bytearray,
    os.PathLike,
)


def stringify(
    nest: object, default: Optional[Callable[[object], object]]
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
    default: Callable[[object], object],
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
    default: Callable[[object], object],
):
    _check_and_update_visited(nest, visited_container)

    dst.append("(" if isinstance(nest, tuple) else "[")
    for v in nest:
        _stringify(v, dst, visited_container, default)
        dst.append(",")
    dst.append(")" if isinstance(nest, tuple) else "]")


def _stringify_keys(
    keys: Iterable[object],
    visited_container: Set[int],
    default: Callable[[object], object],
) -> List[Tuple[str, object]]:
    res: List[Tuple[str, object]] = []

    for k in keys:
        _s: List[str] = []
        _stringify(k, _s, visited_container, default)
        res.append(("".join(_s), k))

    return res


def stringify_mapping(
    nest: Mapping[object, object],
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object],
):
    _check_and_update_visited(nest, visited_container)

    skey_keys = _stringify_keys(nest, visited_container, default)

    try:
        skey_keys.sort()
    except TypeError as e:
        e_ = TypeError("dict in memoization values must have sortable keys")
        raise e_ from e

    dst.append("{")

    for sk, k in skey_keys:
        dst.append(sk)
        dst.append(":")
        _stringify(nest[k], dst, visited_container, default)
        dst.append(",")
    dst.append("}")


def stringify_set(
    nest: Set[object],
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object],
):
    _check_and_update_visited(nest, visited_container)

    skey_keys = _stringify_keys(nest, visited_container, default)

    try:
        skey_keys.sort()
    except TypeError as e:
        e_ = TypeError("set in memoization values must have sortable values")
        raise e_ from e

    dst.append("{")

    for s, _ in skey_keys:
        dst.append(s)
        dst.append(",")

    dst.append(")")


def stringify_atom(
    atom: object,
    dst: List[str],
    visited_container: Set[int],
    default: Callable[[object], object],
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
