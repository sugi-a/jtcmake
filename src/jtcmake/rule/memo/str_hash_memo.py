from __future__ import annotations
from pathlib import PurePath
from hashlib import sha256
from numbers import Complex
from typing import Any, Set, Tuple, List

from ...utils.nest import ordered_map_structure
from .abc import IMemo, IMemoAtom, ILazyMemoValue, IMemoInstance


class StrHashMemo(IMemo):
    def __init__(self, args: object):
        args, lazy_values = unwrap_atom(args)
        self.code = hash_fn(stringify(args))
        self.lazy_values = lazy_values

    @property
    def memo(self) -> StrHashMemoInstance:
        s = stringify([v() for v in self.lazy_values])
        lazy_code = hash_fn(s)
        return StrHashMemoInstance(self.code, lazy_code)


class StrHashMemoInstance(IMemoInstance):
    @classmethod
    def get_type(cls) -> str:
        return "str_hash_memo"

    def __init__(self, code: str, lazy_code: str):
        self.code = code
        self.lazy_code = lazy_code

    def to_obj(self) -> Any:
        return [self.code, self.lazy_code]

    @classmethod
    def from_obj(cls, obj: Any) -> StrHashMemoInstance:
        code, lazy_code = obj
        return StrHashMemoInstance(code, lazy_code)

    def compare(self, other: Any) -> bool:
        if not isinstance(other, StrHashMemoInstance):
            return False

        return (self.code, self.lazy_code) == (other.code, other.lazy_code)


def unwrap_atom(args: Any) -> Tuple[Any, List[ILazyMemoValue]]:
    lazy_values: List[ILazyMemoValue] = []

    def _unwrap_atom(atom: Any):
        if isinstance(atom, IMemoAtom):
            v = atom.memo_value
            if isinstance(v, ILazyMemoValue):
                lazy_values.append(v)
                return None
            else:
                return v
        else:
            return atom

    args = ordered_map_structure(_unwrap_atom, args)

    return args, lazy_values


def hash_fn(s: str):
    return sha256(s.encode("utf8")).digest().hex()


_AUTO_STRINGIFIED_BASE_TYPES = (
    type(None),
    bool,
    bytes,
    bytearray,
    PurePath,
)


def stringify(nest: object) -> str:
    sl: List[str] = []
    visited: Set[int] = set()

    def rec(nest: object):
        if isinstance(nest, (tuple, list, dict, set)):
            if id(nest) in visited:
                raise TypeError("Detected recursion in nested structure")

            visited.add(id(nest))

            if isinstance(nest, (tuple, list)):
                sl.append("(" if isinstance(nest, tuple) else "[")
                for v in nest:  # pyright: ignore [reportUnknownVariableType]
                    rec(v)
                    sl.append(",")
                sl.append(")" if isinstance(nest, tuple) else "]")
            elif isinstance(nest, set):
                try:
                    ordered: List[object] = sorted(nest)
                except TypeError as e:
                    raise TypeError(
                        "set in memoization values must have sortable values"
                    ) from e
                sl.append("{")
                for v in ordered:
                    rec(v)
                    sl.append(",")
                sl.append(")")
            else:
                try:
                    keys: List[object] = sorted(nest)
                except TypeError as e:
                    raise TypeError(
                        "dict in memoization values must have sortable keys"
                    ) from e

                sl.append("{")

                for k in keys:  # pyright: ignore [reportUnknownVariableType]
                    rec(k)
                    sl.append(":")
                    rec(nest[k])
                    sl.append(",")
                sl.append("}")
        elif isinstance(nest, str):
            sl.append(repr(nest))
        elif isinstance(nest, Complex):
            sl.append(str(complex(nest)))
        elif isinstance(nest, _AUTO_STRINGIFIED_BASE_TYPES):
            sl.append(str(nest))
        else:
            ts = (Complex, str, *_AUTO_STRINGIFIED_BASE_TYPES)
            ts = ", ".join(t.__name__ for t in ts)
            raise TypeError(
                f"Every atom element in the memoization values "
                f"must be either {ts}. Given {nest}. \n"
                f"Consider wrapping it using `jtcmake.Atom`. Specifically, "
                f"if stringifying is enough to serialize its state, wrap it "
                f"using `jtcmake.Memstr`, or if you do not need to memoize "
                f"it, consider wrapping it in `jtcmake.Nomem`"
            )

    rec(nest)
    return "".join(sl)
