import sys, os, pathlib, json, re, hashlib, pickle, abc
from ..utils import map_nested, flatten_nested, should_update

NOP = object()


class Rule:
    def __init__(self, name, method, args, kwargs, depset, opaths, ipaths):
        self.name = name
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self.depset = depset
        self.opaths = opaths

        self.ipaths = ipaths


    def should_update_dryrun(self, updated_paths):
        return self.should_update() or any(p in updated_paths for p in self.ipaths)

    def should_update(self):
        return should_update(list(self.opaths), list(self.ipaths))


class IMemoSource(abc.ABC):
    @abc.abstractmethod
    def to_memo(self):
        pass


class MemoSourceFile(IMemoSource):
    def __init__(self, path):
        self.path = path


    def to_memo(self):
        try:
            return _hash_md5(pathlib.Path(self.path).read_bytes())
        except:
            return None


class RuleMemo:
    def __init__(self, name, method, args, kwargs, depset, opaths, ipaths, nested_input, memo_save_path):
        self.name = name
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self.depset = depset
        self.opaths = opaths
        self.ipaths = ipaths

        self.memo_save_path = memo_save_path
        self.nested_input = nested_input


    def should_update_dryrun(self, updated_paths):
        if self.should_update():
            return True

        flatten_inputs = flatten_nested(self.nested_input)
        return any(v.path in updated_paths for v in flatten_inputs if isinstance(p, MemoSourceFile))


    def should_update(self):
        # True if some dst files do not exist
        if any(not os.path.exists(p) for p in self.opaths):
            return True

        memo = _load_memo(self.memo_save_path)
        new_memo = _input_to_memo(self.nested_input)

        return memo != new_memo


    def update_memo(self):
        new_memo = _input_to_memo(self.nested_input)
        _save_memo(self.memo_save_path, new_memo)


def _input_to_memo(x):
    def map_fn(v):
        if isinstance(v, IMemoSource):
            return v.to_memo()
        else:
            return v

    return map_nested(x, map_fn)


def _save_memo(memo_save_path, memo):
    with open(memo_save_path, 'wb') as f:
        pickle.dump(memo, f)


def _load_memo(memo_save_path):
    try:
        with open(memo_save_path, 'rb') as f:
            return pickle.load(f)
    except:
        return None


def _hash_md5(obj):
    m = hashlib.md5()
    try:
        m.update(pickle.dumps(obj))
    except:
        return None
    return m.digest()
