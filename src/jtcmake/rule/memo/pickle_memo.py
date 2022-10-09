from __future__ import annotations
import pickle, hmac

from typing import Any, Optional, Tuple

from .abc import IMemo, IMemoInstance
from .str_hash_memo import unwrap_atom


class PickleMemo(IMemo):
    def __init__(self, args: Any, key: bytes):
        args, lazy_values = unwrap_atom(args)

        code, digest = pickle_encode(args, key)
        self.code = code
        self.digest = digest

        self.key = key
        self.lazy_values = lazy_values

    @property
    def memo(self) -> PickleMemoInstance:
        lcode, ldigest = pickle_encode(
            [v() for v in self.lazy_values], self.key
        )

        return PickleMemoInstance(
            self.code, self.digest, lcode, ldigest, self.key
        )


class PickleMemoInstance(IMemoInstance):
    @classmethod
    def get_type(cls) -> str:
        return "pickle_memo"

    def __init__(
        self,
        code: bytes,
        digest: bytes,
        lcode: bytes,
        ldigest: bytes,
        key: Optional[bytes] = None,
    ):
        self.code = code
        self.digest = digest
        self.lcode = lcode
        self.ldigest = ldigest
        self.key = key

    def to_obj(self) -> Any:
        return {
            "code": self.code.hex(),
            "digest": self.digest.hex(),
            "lcode": self.lcode.hex(),
            "ldigest": self.ldigest.hex(),
        }

    @classmethod
    def from_obj(cls, data: Any) -> PickleMemoInstance:
        return PickleMemoInstance(
            bytes.fromhex(data["code"]),
            bytes.fromhex(data["digest"]),
            bytes.fromhex(data["lcode"]),
            bytes.fromhex(data["ldigest"]),
        )

    def compare(self, other: Any) -> bool:
        if not isinstance(other, PickleMemoInstance):
            return False

        k1_, k2_ = (self.key, other.key)

        if k1_ is None and k2_ is not None:
            k1, k2 = k2_, k2_
        elif k1_ is not None and k2_ is None:
            k1, k2 = k1_, k1_
        elif k1_ is not None and k2_ is not None:
            k1, k2 = k1_, k2_
        else:
            raise Exception(f"Either side must have picke key")

        v11 = pickle_decode(self.code, self.digest, k1)
        v12 = pickle_decode(self.lcode, self.ldigest, k1)
        v21 = pickle_decode(other.code, other.digest, k2)
        v22 = pickle_decode(other.lcode, other.ldigest, k2)

        return (v11, v12) == (v21, v22)


_encode_error_message = (
    "Failed to memoize the arguments by pickling.\n"
    "Every atom in the method arguments must satisfy "
    "the following two conditions:\n\n"
    "1. It must be picklable\n"
    "2. It must be pickle-unpickle invariant, i.e.\n"
    "      unpickle(pickle(atom)) == atom\n"
    "   must hold.\n\n"
    "For example, closures do not satisfy the first condition. "
    "And instances of a class that does not implement a custom "
    "__eq__ do not satisfy the condition 2.\n\n"
    "To pass such an object to the method, wrap it by jtcmake.Atom "
    "like\n"
    '`g.add("rule.txt", func, jtcmake.Atom(lambda x: x*2, None)`'
)


def pickle_encode(obj: Any, key: bytes) -> Tuple[bytes, bytes]:
    try:
        code = pickle.dumps(obj)
    except pickle.PicklingError as e:
        raise Exception(_encode_error_message) from e

    if pickle.loads(code) != obj:
        raise Exception(_encode_error_message)

    return code, create_digest(code, key)


def pickle_decode(code: bytes, digest: bytes, key: bytes):
    if not validate_digest(code, digest, key):
        raise Exception(
            "Authentication error: pickle data was rejected for invalid HMAC"
        )

    return pickle.loads(code)


def create_digest(data: bytes, key: bytes) -> bytes:
    return hmac.new(key, data, "sha256").digest()


def validate_digest(data: bytes, digest: bytes, key: bytes) -> bool:
    """return if digest is valid"""
    ref_digest = create_digest(data, key)
    return hmac.compare_digest(digest, ref_digest)
