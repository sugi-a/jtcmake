import sys, os, hashlib, json, pickle, hashlib, hmac

from ...utils.nest import ordered_map_structure
from .abc import IMemo
from .str_hash_memo import unwrap_atom


_TYPE = "pickle"


class PickleMemo(IMemo):
    def __init__(self, args, key):
        args, lazy_values = unwrap_atom(args)

        code, digest = pickle_encode(args, key)

        self.code = {"value": code.hex(), "digest": digest.hex()}
        self.key = key
        self.lazy_values = lazy_values

    def compare(self, other_memo):
        assert_type_pickle(other_memo["type"])
        return compare_memo(self.memo, other_memo, self.key)

    @property
    def memo(self):
        lcode, ldigest = pickle_encode([v() for v in self.lazy_values], self.key)

        return {
            "type": _TYPE,
            "code": self.code,
            "lazy": {"value": lcode.hex(), "digest": ldigest.hex()},
        }


def assert_type_pickle(type_):
    if type_ != _TYPE:
        raise Exception(f"{_TYPE} memo was expected. Given {type_} memo.")


def compare_memo(a, b, key):
    return compare_code(a["code"], b["code"], key) and compare_code(
        a["lazy"], b["lazy"], key
    )


def compare_code(a, b, key):
    fromhex = bytes.fromhex
    a = pickle_decode(fromhex(a["value"]), fromhex(a["digest"]), key)
    b = pickle_decode(fromhex(b["value"]), fromhex(b["digest"]), key)

    return a == b


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


def pickle_encode(obj, key):
    try:
        code = pickle.dumps(obj)
    except pickle.PicklingError as e:
        raise Exception(_encode_error_message) from e

    if pickle.loads(code) != obj:
        raise Exception(_encode_error_message)

    return code, create_digest(code, key)


def pickle_decode(code, digest, key):
    if not validate_digest(code, digest, key):
        raise Exception(
            "Authentication error: pickle data was rejected for invalid HMAC"
        )

    return pickle.loads(code)


def create_digest(data, key):
    return hmac.new(key, data, "sha256").digest()


def validate_digest(data, digest, key):
    """return if digest is valid"""
    ref_digest = create_digest(data, key)
    return hmac.compare_digest(digest, ref_digest)
