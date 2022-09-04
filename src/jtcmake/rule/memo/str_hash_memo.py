from pathlib import PurePath
from hashlib import sha256
from numbers import Complex

from ...utils.nest import ordered_map_structure
from .abc import IMemo, IMemoAtom, ILazyMemoValue
from ...frontend.atom import Atom

_TYPE = "str-hash"


class StrHashMemo(IMemo):
    def __init__(self, args):
        args, lazy_values = unwrap_atom(args)

        self.code = hash_fn(stringify(args))
        self.lazy_values = lazy_values

    def compare(self, memo):
        if memo["type"] != _TYPE:
            raise Exception(f'Expected {_TYPE} memo. Given {memo["type"]} memo. ')

        return memo == self.memo

    @property
    def memo(self):
        s = stringify([v() for v in self.lazy_values])
        lazy_code = hash_fn(s)
        res = {"type": _TYPE, "code": self.code, "lazy": lazy_code}
        return res


def unwrap_atom(args):
    lazy_values = []

    def _unwrap_atom(atom):
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


def hash_fn(s):
    return sha256(s.encode("utf8")).digest().hex()


_AUTO_STRINGIFIED_BASE_TYPES = (
    type(None),
    bool,
    bytes,
    bytearray,
    PurePath,
)


def stringify(nest):
    sl = []
    visited = set()

    def rec(nest):
        if isinstance(nest, (tuple, list, dict, set)):
            if id(nest) in visited:
                raise TypeError("Detected recursion in nested structure")

            visited.add(id(nest))

            if isinstance(nest, (tuple, list)):
                sl.append("(" if isinstance(nest, tuple) else "[")
                for v in nest:
                    rec(v)
                    sl.append(",")
                sl.append(")" if isinstance(nest, tuple) else "]")
            elif isinstance(nest, set):
                try:
                    ordered = sorted(nest)
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
                    keys = sorted(nest)
                except TypeError as e:
                    raise TypeError(
                        "dict in memoization values must have sortable keys"
                    ) from e

                sl.append("{")

                for k in keys:
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
