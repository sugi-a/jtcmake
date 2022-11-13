from __future__ import annotations
import os
import json
from hashlib import sha256
from abc import ABCMeta, abstractmethod
from numbers import Complex
from typing import (
    Callable,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    List,
    Union,
)

from .raw_rule import IMemo


ENCODING = "utf8"


class ILazyMemo(IMemo, metaclass=ABCMeta):
    @property
    def memo(self) -> IMemo:
        ...

    @property
    def lazy_memo(self) -> IMemo:
        ...

    @classmethod
    @abstractmethod
    def create(cls, args: object, lazy_args: Callable[[], object]) -> ILazyMemo:
        ...


def create_lazy_memo_type(
    memo_factory: Callable[[object], IMemo]
) -> Type[ILazyMemo]:
    from_bytes = memo_factory(None).loads

    class LazyMemo(ILazyMemo):
        __slots__ = ("_memo", "lazy_args")
        _memo: IMemo
        lazy_args: Union[Callable[[], object], IMemo]

        def __init__(
            self,
            memo: IMemo,
            lazy_args: Union[Callable[[], object], IMemo],
        ):
            self._memo = memo
            self.lazy_args = lazy_args

        @property
        def memo(self) -> IMemo:
            return self._memo

        @property
        def lazy_memo(self) -> IMemo:
            if isinstance(self.lazy_args, IMemo):
                return self.lazy_args
            else:
                return memo_factory(self.lazy_args())

        def compare(self, other: IMemo) -> bool:
            if isinstance(other, ILazyMemo):
                return self.memo.compare(other.memo) and self.lazy_memo.compare(
                    other.lazy_memo
                )
            else:
                return False

        @classmethod
        def create(
            cls, args: object, lazy_args: Callable[[], object]
        ) -> ILazyMemo:
            return cls(memo_factory(args), lazy_args)

        def dumps(self) -> Iterable[bytes]:
            memo_ = b"".join(self.memo.dumps()).hex()
            lazy_memo_ = b"".join(self.lazy_memo.dumps()).hex()
            return [json.dumps([memo_, lazy_memo_]).encode(ENCODING)]

        @classmethod
        def loads(cls, data: bytes) -> ILazyMemo:
            o = json.loads(data.decode(ENCODING))
            assert isinstance(o, list)

            memo = from_bytes(bytes.fromhex(o[0]))
            lazy_args = from_bytes(bytes.fromhex(o[1]))

            return cls(memo, lazy_args)

    return LazyMemo


MAX_RAW_REPRESENTATION_LEN = 1000


class StrHashMemo(IMemo):
    __slots__ = ("text",)
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

    def dumps(self) -> Iterable[bytes]:
        return [self.text.encode(ENCODING)]

    @classmethod
    def loads(cls, data: bytes) -> StrHashMemo:
        return cls(data.decode(ENCODING))

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
