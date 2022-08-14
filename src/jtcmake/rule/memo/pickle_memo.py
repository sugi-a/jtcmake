import sys, os, hashlib, json, pickle, hashlib, hmac

from .imemo import IMemo


_TYPE = 'pickle'

class PickleMemo(IMemo):
    def __init__(self, args, key):
        code, digest = pickle_encode(args, key)
        self._memo = {
            'type': _TYPE, 'code': code.hex(), 'digest': digest.hex()
        }
        self.key = key


    def compare(self, memo):
        if memo['type'] != _TYPE:
            raise Exception(
                f'Type of the given memo is {memo["type"]} where '
                f'{_TYPE} was expected'
            )

        code = bytes.fromhex(memo['code'])
        digest = bytes.fromhex(memo['digest'])
        old_args = pickle_decode(code, digest, self.key)

        return old_args == pickle.loads(bytes.fromhex(self.memo['code']))


    @property
    def memo(self):
        return self._memo


_encode_error_message = (
    'Failed to memoize the arguments by pickling.\n'
    'Every atom in the method arguments must satisfy '
    'the following two conditions:\n\n'
    '1. It must be picklable\n'
    '2. It must be pickle-unpickle invariant, i.e.\n'
    '      unpickle(pickle(atom)) == atom\n'
    '   must hold.\n\n'
    'For example, closures do not satisfy the first condition. '
    'And instances of a class that does not implement a custom '
    '__eq__ do not satisfy the condition 2.\n\n'
    'To pass such an object to the method, wrap it by jtcmake.Atom '
    'like\n'
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
            'Authentication error: pickle data was rejected for invalid HMAC'
        )

    return pickle.loads(code)


def create_digest(data, key):
    return hmac.new(key, data, 'sha256').digest()


def validate_digest(data, digest, key):
    """return if digest is valid"""
    ref_digest = create_digest(data, key)
    return hmac.compare_digest(digest, ref_digest)

