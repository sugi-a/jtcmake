import sys, os, pathlib, re, contextlib, time, json, inspect
from abc import ABC, abstractmethod
import itertools
from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path, WindowsPath, PosixPath
from logging import Logger

from ..rule.rule import Rule as _RawRule
from ..rule.memo import PickleMemo, StrHashMemo
from ..rule.file import File, VFile, IFile
from .event_logger import log_make_event
from ..core.make import make as _make, MakeSummary
from ..core.make_mp import make_mp_spawn
from ..logwriter.writer import (
    TextWriter,
    ColorTextWriter,
    HTMLJupyterWriter,
    term_is_jupyter,
    TextFileWriterOpenOnDemand,
    HTMLFileWriterOpenOnDemand,
    LoggerWriter,
    WritersWrapper,
    RichStr,
)

from .atom import Atom

from ..utils.nest import (
    NestKey,
    map_structure,
    flatten,
    nest_get,
    flatten_to_nest_keys,
    pack_sequence_as,
)

from ..utils.frozen_dict import FrozenDict


# dict and FrozenDict are the map-type target of map_structure
_MAP_FACTORY = {(dict, FrozenDict): dict}


_Path = WindowsPath if os.name == 'nt' else PosixPath

def _touch(path, create, _t, logwriter):
    path = str(path)

    if not os.path.exists(path) and create:
        try:
            open(path, "w").close()
        except Exception:
            return

    if os.path.exists(path):
        os.utime(path, (_t, _t))
        logwriter.info("touch ", RichStr(path, link=path), "\n")


def _clean(path, logwriter):
    path = str(path)

    try:
        os.remove(path)
        logwriter.info("clean ", RichStr(path, link=path), "\n")
    except:
        pass


class GroupTreeInfo:
    def __init__(self, logwriter, memo_factory):
        self.rules = []  # list<Rule>
        self.rule2idx = {}  # dict<int, int>
        self.path2idx = {}  # dict<Path, int>. idx can be -1
        self.idx2xpaths = []  # list<list<Path>>
        self.path2file = {}  # dict<str, IFile>
        self.memo_factory = memo_factory

        self.logwriter = logwriter

        self.memo_store = {}  # dict<int, (any, any)>


class _ItemSet(Mapping):
    def __init__(self, dic):
        self._dic = dic

    def __getitem__(self, k):
        return self._dic[k]

    def __getattr__(self, k):
        return self._dic[k]

    def __iter__(self):
        return iter(self._dic)

    def __len__(self):
        return len(self._dic)

    def __contains__(self, k):
        return k in self._dic

    def __eq__(self, other):
        return id(self) == id(other)

    def __hash__(self):
        return hash(id(self))

    def _add(self, k, v):
        self._dic[k] = v


class _Self:
    def __init__(self, key=None):
        self._key = key

    def __getitem__(self, key):
        return _Self(key)

    def __getattr__(self, key):
        return self[key]

    def __repr__(self):
        if self._key is None:
            return "Self"
        else:
            return f"Self({self._key})"


SELF = _Self()


class Rule(FrozenDict):
    def __init__(self, name, files, rrule, group_tree_info):
        super().__init__(files)
        self._rrule = rrule
        self._info = group_tree_info
        self._name = name

    def make(
        self,
        dry_run=False,
        keep_going=False,
        *,
        njobs=None,
    ):
        """Make this rule and its dependencies
        Args:
            dry_run:
                instead of actually excuting the methods,
                print expected execution logs.
            keep_going:
                If False (default), stop everything when a rule fails.
                If True, when a rule fails, keep executing other rules
                except the ones depend on the failed rule.
            njobs:
                Maximum number of rules that can be made concurrently.
                Defaults to 1 (single process, single thread).

        See also:
            See the description of jtcmake.make for more detail of njobs
        """
        return make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            njobs=njobs,
        )

    @property
    def name(self):
        return self._name

    def touch_memo(self):
        """
        Overwrite memo based on the current content of the method arguments.
        """
        self._rrule.update_memo()

    def touch(self, create=False, _t=None):
        """
        Set the modification time of the output files of this rule to now.

        Args:
            create (bool): if True, files that do not exist will be
                created as empty files.
            _t (float):
                set mtime to `_t` instead of now
        """
        if _t is None:
            _t = time.time()

        for k in self:
            _touch(self[k], create, _t, self._info.logwriter)

    def clean(self):
        """
        Delete the output files and the memo of this rule.
        """
        for k in self:
            _clean(self[k], self._info.logwriter)


    def __eq__(self, other):
        return id(self) == id(other)


    def __hash__(self):
        return hash(id(self))


def _parse_args_group_add(args, kwargs, file_factory):
    """
    Extracted values:
        name (str): name of the rule
        outs (Dict[str, IFile]): output files (name -> path)
        method (Callable[P, T]|None): method
        *args: positional arguments for the method
        **kwargs: keyward arguments for the method
    """
    if len(args) <= 1:
        raise TypeError(
            f"At least two arguments are expected. Given {len(args)}."
        )

    if args[1] is None or callable(args[1]):
        outs, method, *args = args
        name = None
    else:
        if len(args) == 2 or not (args[2] is None or callable(args[2])):
            raise TypeError("Method must be specified")

        name, outs, method, *args = args

    # validate and normalize output files
    if isinstance(outs, (tuple, list)):
        outs = { str(v): v for v in outs }
    elif isinstance(outs, (str, Path)):
        outs = { str(outs): outs }
    elif isinstance(outs, dict):
        pass
    else:
        raise TypeError(
            'Expected tuple[str|PathLike), list[str|PathLike], '
            f'dict[str, str|PathLike], str, or PathLike. Given {outs}'
        )

    for k in outs:
        if not isinstance(k, str):
            raise TypeError(f'Keys of output dict must be str. Given {k}')

    def _to_ifile(f):
        if isinstance(f, IFile):
            return f

        if isinstance(f, (str, os.PathLike)):
            return file_factory(f)

        raise TypeError(f'Output file must be str or PathLike. Given {f}')

    outs = { k: _to_ifile(v) for k, v in outs.items() }

    if len(outs) == 0:
        raise TypeError('At least 1 output file must be specified')

    # validate name
    if name is None:
        name = str(next(iter(outs)))
    else:
        if not isinstance(name, str):
            raise TypeError(f'name must be str')

    return name, outs, method, args, kwargs


def _validate_signature(func, args, kwargs):
    try:
        binding = inspect.signature(func).bind(*args, **kwargs)
    except Exception as e:
        return False

    return True


def _shorter_path(p):
    cwd = os.getcwd()

    if os.name == "posix":
        p = Path(os.path.expanduser(p))

    try:
        rel = Path(os.path.relpath(p, cwd))
        return rel if len(str(rel)) < len(str(p)) else p
    except Exception:
        return p


class Group:
    """
    __init__() for this class is private.
    Use create_group() instead to instanciate it.
    """

    def __init__(self, info, prefix, name):
        if not isinstance(prefix, str):
            raise TypeError("prefix must be str")

        self._info = info
        self._prefix = prefix
        self._name = name

        self._rules = _ItemSet({})
        self._files = _ItemSet({})
        self._groups = _ItemSet({})

    @property
    def G(self):
        return self._groups

    @property
    def R(self):
        return self._rules

    @property
    def F(self):
        return self._files

    def mem(self, value, memoized_value):
        # reference: root Group -> memo_store -> atom -> value
        # so value won't be GC'ed and id is valid while group tree is active
        self._info.memo_store[id(value)] = Atom(value, memoized_value)
        return value


    def memstr(self, value):
        return self.mem(value, str(value))


    def memnone(self, value):
        return self.mem(value, None)


    def add_group(self, name, dirname=None, *, prefix=None):
        """Add a child Group node

        Args:
            name (str|os.PathLike): name of the node.
            dirname (str|os.PathLike): directory for the node.
            prefix (str|os.PathLike): path prefix for the node.

                - At most one of dirname and prefix can be specified
                - If both dirname and prefix are None, then name will be used
                  as dirname
                - The following two are equivalent:
                    - `Group.add_group('name', dirname='dir')`
                    - `Group.add_group('name', prefix='dir/')`

        Returns:
            Group node
        """
        if isinstance(name, os.PathLike):
            name = name.__fspath__()
        elif not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        if name in self._groups:
            raise KeyError(f"name {repr(name)} already exists in this Group")

        if not _is_valid_node_name(name):
            raise ValueError(f'name "{name}" contains some illegal characters')

        if name == "":
            raise ValueError(f'name must not be ""')

        if dirname is not None and prefix is not None:
            raise TypeError("Either dirname or prefix can be specified")

        if dirname is None and prefix is None:
            dirname = name

        if dirname is not None:
            assert isinstance(dirname, (str, os.PathLike))
            prefix = str(Path(dirname)) + os.path.sep

        assert isinstance(prefix, (str, os.PathLike))

        if os.name == "posix":
            prefix = os.path.expanduser(prefix)

        if isinstance(prefix, os.PathLike):
            prefix = prefix.__fspath__()

        if not os.path.isabs(prefix):
            prefix = self._prefix + prefix

        g = Group(self._info, prefix, (*self._name, name))

        self._groups._add(name, g)

        if name.isidentifier() and name[0] != '_' and not hasattr(self, name):
            self.__dict__[name] = g
            

        return g

    def make(
        self,
        dry_run=False,
        keep_going=False,
        *,
        njobs=None,
    ):
        """Make rules in this group and their dependencies

        Args:
            dry_run (bool):
                instead of actually excuting the methods,
                print expected execution logs.
            keep_going (bool):
                If False (default), stop everything when a rule fails.
                If True, when a rule fails, keep executing other rules
                except the ones depend on the failed rule.
            njobs (int):
                Maximum number of rules that can be made concurrently.
                Defaults to 1 (single process, single thread).

        See also:
            See the description of jtcmake.make for more detail of njobs
        """
        return make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            njobs=njobs,
        )

    # APIs
    def add(self, *args, **kwargs):
        """Add a Rule node into this Group node.

        Call signatures:

            1. `add(name, [output_files], method, *args, **kwargs)`
            2. `add(name, [output_files], None, *args, **kwargs)`

        Args:
            name (str|os.PathLike): Name for the Rule
            output_files:
                Nested structure representing the output files of the Rule.
                A leaf node of the structure may be either str, os.PathLike,
                or IFileBase (including File and VFile).
            method (Callable):
                Will be called as `method(*args, **kwargs)` on update

        Returns:
            RuleNodeLike
            RuleNodeAtom|RuleNodeTuple|RuleNodeDict|Callable[Callable, RuleNodeAtom|RuleNodeTuple|RuleNodeDict]: aaa `Group`

        Call signature (2) is for decorator-style adding.
            The following two are equivalent:
            `Group.add(name, output_files, None, *args, **kwargs)(method)`
            `Group.add(name, output_files, method, *args, **kwargs)`

        How Group.add differs from Group.addvf:
            Default IFileBase type used to wrap the nodes in
            output_files whose type is str or os.PathLike is different.
            - Group.add wraps them by File.
            - Group.addvf wraps them by VFile.
        """
        name, path, method, args, kwargs = \
            _parse_args_group_add(args, kwargs, File)

        if method is None:
            def decorator_add(method):
                self._add(name, path, method, args, kwargs)
                return method

            return decorator_add
        else:
            return self._add(name, path, method, args, kwargs)


    def addvf(self, *args, **kwargs):
        """Add a Rule node into this Group node.

        Call signatures:

            1. `add(name, [output_files], method, *args, **kwargs)`
            2. `add(name, [output_files], None, *args, **kwargs)`

        Args:
            name (str|os.PathLike): Name for the Rule
            output_files:
                Nested structure representing the output files of the Rule.
                A leaf node of the structure may be either str, os.PathLike,
                or IFileBase (including File and VFile).
            method (Callable):
                Will be called as `method(*args, **kwargs)` on update

        Returns (1):
            Rule node (Union[RuleNodeAtom, RuleNodeTuple, RuleNodeDict])

        Returns (2):
            A function (method: Callable) -> RuleNode.

        Call signature (2) is for decorator-style adding.
            The following two are equivalent:
            `Group.add(name, output_files, None, *args, **kwargs)(method)`
            `Group.add(name, output_files, method, *args, **kwargs)`

        How Group.add differs from Group.addvf:
            Default IFileBase type used to wrap the nodes in
            output_files whose type is str or os.PathLike is different.
            - Group.add wraps them by File.
            - Group.addvf wraps them by VFile.
        """
        name, path, method, args, kwargs = \
            _parse_args_group_add(args, kwargs, VFile)

        if method is None:
            def decorator_addvf(method):
                self._add(name, path, method, args, kwargs)
                return method

            return decorator_addvf
        else:
            return self._add(name, path, method, args, kwargs)

    def add2(self, *args):
        name, outs, method, args, kwargs = \
            _parse_args_group_add(args, {}, File)

        if len(args) != 0:
            raise TypeError(f"Too many arguments: {args}")

        if len(kwargs) != 0:
            raise TypeError(f"Too many arguments: {kwargs}")

        if method is None:
            raise TypeError(f"method must be specified")

        def _adder(*args, **kwargs):
            self._add(name, outs, method, args, kwargs)

        return _adder


    def _add(self, name, yfiles, method, args, kwargs):
        abspath = os.path.abspath
        info = self._info

        if not _is_valid_node_name(name):
            raise ValueError(f'name "{name}" contains some illegal characters')
        if name == "":
            raise ValueError(f'name must not be ""')

        if name in self._rules:
            raise KeyError(f"name `{name}` already exists in the group")

        for alias, f in yfiles.items():
            if alias in self._files:
                raise KeyError(f"Alias '{alias}' already exists in the group")

        # expand ~
        if os.name == "posix":
            yfiles = {
                k: f.replace(os.path.expanduser(f)) for k, f in yfiles.items()
            }

        # add prefix to paths if not absolute
        yfiles = {
            k: f if f.is_absolute() else f.replace(self._prefix + str(f))
            for k, f in yfiles.items()
        }

        yfiles = { k: f.replace(_shorter_path(f)) for k, f in yfiles.items() }

        # check yfile duplicated registration and type consistency
        yp2f = {}
        for k, f in yfiles.items():
            _absp = abspath(f)

            if _absp in info.path2idx:
                raise ValueError(
                    f"File {_absp} is already used in the group tree"
                )

            if _absp in yp2f and type(yp2f[_absp]) != type(f):
                raise TypeError(
                    "IFile type inconsistency found: Output files "
                    f"contains more than one IFiles pointing to {_absp} "
                    f"with different types: {type(f)} and {type(yp2f[_absp])}"
                )

            yp2f[_absp] = f

        # reserved Atom replacement
        def _rec(o):
            if id(o) in info.memo_store:
                return info.memo_store[id(o)]
            elif isinstance(o, dict):
                return { k: _rec(v) for k, v in o.items() }
            elif isinstance(o, tuple):
                return tuple(map(_rec, o))
            elif isinstance(o, list):
                return list(map(_rec, o))
            else:
                return o

        args, kwargs = _rec((args, kwargs))

        # flatten args
        try:
            args_ = flatten((args, kwargs))
        except Exception as e:
            raise Exception("Failed to flatten args and kwargs.") from e

        # replace SELFs with the corresponding output files
        def _repl_self(o):
            if isinstance(o, _Self):
                if o._key is None:
                    if len(yfiles) >= 2:
                        raise TypeError(
                            "Self-without-key is not allowed when the "
                            "rule has multiple output files"
                        )
                    a = next(iter(yfiles.values()))
                    return a
                else:
                    if o._key not in yfiles:
                        raise KeyError(f"Failed to resolve Self: {o._key}")
                    return yfiles[o._key]
            else:
                return o

        args_ = list(map(_repl_self, args_))

        files = list(filter(lambda f: isinstance(f, IFile), args_))

        # check type consistency and coverage of output files in arguments
        _unused_yp = set(yp2f)
        xp2f = {}

        for f in files:
            _absp = abspath(f)

            if _absp in yp2f:
                if type(yp2f[_absp]) != type(f):
                    raise TypeError(
                        "IFile type inconsistency found: two IFiles "
                        f"pointing to {_absp} have different types "
                        f"{type(f)} and {type(yp2f[_absp])}"
                    )

                if _absp in _unused_yp:
                    _unused_yp.remove(_absp)
            else:
                # inconsistency with the existing files
                _f = info.path2file.get(_absp)
                if _f and type(_f) != type(f):
                    raise TypeError(
                        f"IFile inconsistency found: argument {f} is of type "
                        f"({type(f)}) but the group tree already has "
                        f"{_f} of type {type(_f)}"
                    )

                # inconsistency
                if _absp in xp2f and type(xp2f[_absp]) != type(f):
                    raise TypeError(
                        "IFile inconsistency found: argument {f} is of type "
                        f"({_absp}) must have the same type but "
                        f"One is {type(f)} and the other is {xp2f[_absp]}"
                    )

                xp2f[_absp] = f

        if len(_unused_yp) != 0:
            _missings = [yp2f[p] for p in _unused_yp]
            raise Exception(
                "All the output files must be included in the arguments. "
                f"Missing ones are: {_missings}"
            )

        # create deplist
        deplist = [
            info.path2idx[p] for p in xp2f if info.path2idx.get(p, -1) != -1
        ]
        dpelist = list(set(deplist))

        # create xfiles
        xfiles = list(xp2f.values())
        xfile_is_orig = [info.path2idx.get(p, -1) == -1 for p in xp2f]

        # create method args
        def _unwrap_Atom(x):
            if isinstance(x, Atom):
                return x.value
            else:
                return x

        method_args = pack_sequence_as((args, kwargs), args_)
        method_args = map_structure(_unwrap_Atom, method_args)
        method_args, method_kwargs = method_args

        # validate arguments
        if not _validate_signature(method, method_args, method_kwargs):
            raise TypeError("arguments do not match the method signature")

        memo_args = pack_sequence_as((args, kwargs), args_)
        memo = info.memo_factory(memo_args)

        # create Rule
        _rrule = _RawRule(
            list(yp2f.values()),
            xfiles,
            xfile_is_orig,
            deplist,
            method,
            method_args,
            method_kwargs,
            memo=memo,
            name=(*self._name, name),
        )

        # create RuleNode
        rule = Rule((*self._name, name), yfiles, _rrule, info)

        # update group tree
        self._rules._add(name, rule)

        for alias, f in yfiles.items():
            assert alias not in self._files
            self._files._add(alias, f)

        rule_idx = len(self._info.rules)
        info.rules.append(_rrule)
        info.rule2idx[_rrule] = rule_idx

        assert len(info.rules) == len(info.rule2idx)

        for p in yp2f:
            info.path2idx[p] = rule_idx

        for p in xp2f:
            if p not in info.path2idx:
                # original file
                info.path2idx[p] = -1

        for p, f in itertools.chain(xp2f.items(), yp2f.items()):
            info.path2file[p] = f

        info.idx2xpaths.append(list(xp2f))

        return rule

    def clean(self):
        """Delete files under this Group"""
        for c in self.G.values():
            c.clean()

        for r in self.R.values():
            r.clean()

    def touch(self, create=False, _t=None):
        """Touch files under this Group

        Args:
            create (bool):
                if False (default), skip the file if it does not exist.
            _t (float):
                set mtime to `_t` after touching
        """
        if _t is None:
            _t = time.time()

        for c in self.G.values():
            c.touch(create, _t)

        for r in self.R.values():
            r.touch(create, _t)

    def _get_offspring_groups(self, dst):
        for k, c in self._groups.items():
            dst.append(c)
            c._get_offspring_groups(dst)

    def _select_wrapper(self, pattern, kind):
        if isinstance(pattern, str):
            if len(pattern) == 0:
                raise ValueError('pattern must not be an empty str')

            pattern = pattern.strip("/")
            pattern = re.split("/+", pattern)
        elif isinstance(pattern, (tuple, list)):
            if not all(isinstance(v, str) for v in pattern):
                raise TypeError("Pattern sequence items must be str")
        else:
            raise TypeError("Pattern must be str or sequence of str")

        return self._select(pattern, kind)

    def _select(self, pattern, kind):
        SEP = ";"
        regex = []
        for p in pattern:
            assert len(p) > 0

            if p.find("**") != -1 and p != "**":
                raise ValueError(
                    'Invalid pattern: "**" can only be an entire component'
                )
            if p == "**":
                regex.append(f"({SEP}[^{SEP}]+)*")
            else:
                if p == "*":
                    # single * does not match an empty str
                    regex.append(f"{SEP}[^{SEP}]+")
                else:

                    def _repl(x):
                        x = x.group()
                        return f"[^{SEP}]*" if x == "*" else re.escape(x)

                    p = re.sub(r"\*|[^*]+", _repl, p)
                    regex.append(f"{SEP}{p}")

        regex = re.compile("^" + "".join(regex) + "$")

        offspring_groups = [self]
        self._get_offspring_groups(offspring_groups)

        if kind == "group":
            target_names = [n._name for n in offspring_groups]
            targets = offspring_groups

        elif kind == "rule":
            _a = list(itertools.chain(
                *(
                    tuple((n.R[name], (*n._name, name)) for name in n.R)
                    for n in offspring_groups
                )
            ))
            targets = [a[0] for a in _a]
            target_names = [a[1] for a in _a]
        elif kind == "file":
            _a = list(itertools.chain(
                *(
                    tuple((n.F[name], (*n._name, name)) for name in n.F)
                    for n in offspring_groups
                )
            ))
            targets = [a[0] for a in _a]
            target_names = [a[1] for a in _a]
        else:
            raise Exception("unreachable")

        res = []
        for target, target_name in zip(targets, target_names):
            target_name = target_name[len(self._name) :]
            if regex.match("".join(SEP + n for n in target_name)):
                res.append(target)

        return res

    def select_rules(self, pattern):
        return self._select_wrapper(pattern, "rule")

    def select_files(self, pattern):
        return self._select_wrapper(pattern, "file")

    def select_groups(self, pattern):
        """Obtain child groups or rules of this group.

        Signatures:

            1. `select(group_tree_pattern: str)`
            2. `select(group_tree_pattern: Sequence[str], group:bool=False)`

        Args for Signature 1:
            group_tree_pattern (str):
                Pattern of the relative name of child nodes of this group.
                Pattern consists of names concatenated with the delimiter '/'.
                Double star '**' can appear as a name indicating zero or
                more repetition of arbitrary names.

                Single star can appear as a part of a name indicating zero
                or more repetition of arbitrary character.

                If `group_tree_pattern[-1] == '/'`, it matches groups only.
                Otherwise, it matches rules only.

                For example, calling g.select(pattern) with a pattern

                * `"a/b"  matches a rule `g.a.b`
                * "a/b/" matches a group `g.a.b`
                * "a*"   matches rules `g.a`, `g.a1`, `g.a2`, etc
                * "a*/"  matches groups `g.a`, `g.a1`, `g.a2`, etc
                * `"**"`   matches all the offspring rules of `g`
                * `"**/"`  matches all the offspring groups of `g`
                * `"a/**"` matches all the offspring rules of the group `g.a`
                * `"**/b"` matches all the offspring rules of `g` with a name "b"

            group: ignored

        Args for Signature-2:
            group_tree_pattern (list[str] | tuple[str]):
                Pattern representation using a sequence of names.

                Following two are equivalent:

                * `g.select(["a", "*", "c", "**"])`
                * `g.select("a/*/c/**")`

                Following two are equivalent:

                * `g.select(["a", "*", "c", "**"], True)`
                * `g.select("a/*/c/**/")`

            group (bool):
                if False (default), select rules only.
                if True, select groups only.

        Returns:
            list[RuleNodeLike]|list[Group]: rule nodes or group nodes.

            * called with Signature-1 and pattern[-1] != '/' or
            * called with Signature-2 and group is False

        Note:
            Cases where Signature-2 is absolutely necessary is when you need
            to select a node whose name contains "/".
            For example, ::

                g = create_group('group')
                rule = g.add('dir/a.txt', func)  # this rule's name is "dir/a.txt"

                g.select(['dir/a.txt']) == [rule]  # OK
                g.select('dir/a.txt') != []  # trying to match g['dir']['a.txt']
        """
        return self._select_wrapper(pattern, "group")

    def __repr__(self):
        name = repr_group_name(self._name)
        return f"<Group name={repr(name)} prefix={repr(self._prefix)}>"

    def __getitem__(self, k):
        return self.G[k]

    def __iter__(self):
        return iter(self.G)

    def __len__(self):
        return len(self.G)

    def __contains__(self, k):
        return k in self.G


def repr_group_name(group_name):
    return "/" + "/".join(map(str, group_name))


def repr_rule_name(trg_name):
    return repr_group_name(trg_name[:-1]) + ":" + str(trg_name[-1])


def _ismembername(name):
    return isinstance(name, str) and name.isidentifier() and name[0] != "_"


def _is_valid_node_name(name):
    # Group.select() depends on ':' being invalid
    return not re.search('[;*?"<>|]', name)


def make(*rule_or_groups, dry_run=False, keep_going=False, njobs=None):
    """make rules

    Args:
        rules_or_groups (Sequence[RuleNodeBase|Group]):
            Rules and Groups containing target Rules
        dry_run:
            instead of actually excuting methods, print expected execution logs.
        keep_going:
            If False (default), stop everything when a rule fails.
            If True, when a rule fails, keep executing other rules
            except the ones depend on the failed rule.
        njobs:
            Maximum number of rules that can be made concurrently.
            Defaults to 1 (single process, single thread).

            Note that safely using njobs >= 2 and fully exploiting the power
            of multi-core processors require a certain level of
            understanding of Python's threading and multiprocessing.

            Each rule is made on a child process if it is transferable.
            A rule is "transferable" if both of the following conditions
            are met:

            - method/args/kwargs of the rule are all picklable
            - Pickle representation of method/args/kwargs created in the
              main process is unpicklable in child processes

            If a rule is not transferable, it is made on a sub-thread of
            the main process. Thus the method must be thread-safe. Also note
            that methods running on the main process are subject to the
            global interpreter lock (GIL) constraints.

            Child processes are started by the 'spawn' method, not 'fork',
            even on Linux systems.
            njobs >= 2 may not work on interactive interpreters.
            It should work on Jupyter Notebook/Lab but any function or class
            that are defined on the notebook is not transferable and thus
            executed in the main process.
    """

    # create list of unique rules by DFS
    _added = set()

    if len(rule_or_groups) == 0:
        return MakeSummary(total=0, update=0, skip=0, fail=0, discard=0)

    _info = rule_or_groups[0]._info

    def _assert_same_tree(node):
        if node._info is not _info:
            raise ValueError(
                "All Groups/Rules must belong to the same Group tree. "
            )

    list(map(_assert_same_tree, rule_or_groups))

    rules = [r._rrule for r in rule_or_groups if isinstance(r, Rule)]
    stack = [g for g in reversed(rule_or_groups) if isinstance(g, Group)]

    assert len(rules) + len(stack) == len(rule_or_groups)

    while stack:
        node = stack.pop()
        stack.extend(node.G.values())
        rules.extend(r._rrule for r in node.R.values())

        list(map(_assert_same_tree, node.G.values()))
        list(map(_assert_same_tree, node.R.values()))

    ids = [_info.rule2idx[r] for r in rules]

    def callback_(event):
        log_make_event(_info.logwriter, event)

    if njobs is not None and njobs >= 2:
        return make_mp_spawn(
            _info.rules, ids, dry_run, keep_going, callback_, njobs
        )
    else:
        return _make(_info.rules, ids, dry_run, keep_going, callback_)


def create_group(
    dirname=None,
    prefix=None,
    *,
    loglevel=None,
    use_default_logger=True,
    logfile=None,
    memo_kind="str_hash",
    pickle_key=None,
):
    """Create a root Group node.

    Args:
        dirname (str|os.PathLike): directory name for this Group node.
        prefix (str|os.PathLike): path prefix for this Group node.
            Either (but not both) dirname or prefix must be specified.
            The following two are equivalent:

            1. `create_group(dirname='dir')`
            2. `create_group(prefix='dir/')`

        loglevel (str|None):
            log level. Defaults to "info".
            Choices are "debug", "info", "warning", "error".

        use_default_logger (bool): If True, logs will be printed to terminal.
            Defaults to True.
        logfile (None, str | os.PathLike | logging.Logger | writable-stream Sequence[str | os.PathLike | logging.Logger | writable-stream]):
            If specified, logs are printed to the file(s), stream(s), or
            logger(s). str values are considered to be file names,
            and if the file extension is .html, logs will be printed in
            HTML format.
        pickle_key (bytes|str||None): key used to authenticate pickle data.
            If str, it must be a hexadecimal str, and will be converted to
            bytes by `bytes.fromhex(pickle_key)`.
            If None, the default pickle key will be used. You can configure
            the default by `jtcmake.set_default_pickle_key(key)`

    Returns:
        Group: Root group node
    """
    if (dirname is None) == (prefix is None):
        raise TypeError("Either dirname or prefix must be specified")

    if dirname is not None:
        assert isinstance(dirname, (str, os.PathLike))
        prefix = str(dirname) + os.path.sep

    assert isinstance(prefix, (str, os.PathLike))

    if os.name == "posix":
        prefix = os.path.expanduser(prefix)

    loglevel = loglevel or "info"

    if logfile is None:
        logfiles = []
    elif isinstance(logfile, (list, tuple)):
        logfiles = logfile
    else:
        logfiles = [logfile]

    _writers = [_create_logwriter(f, loglevel) for f in logfiles]

    if use_default_logger:
        _writers.append(_create_default_logwriter(loglevel))

    logwriter = WritersWrapper(_writers)

    if memo_kind == "pickle":
        if pickle_key is None:
            raise TypeError(
                'pickle_key must be specified when memo_kind is "pickle"'
            )

        memo_factory = _get_memo_factory_pickle(pickle_key)
    elif memo_kind == "str_hash":
        if pickle_key is not None:
            raise TypeError(
                "pickle_key must not be specified for "
                "str_hash memoization method"
            )
        memo_factory = _memo_factory_str_hash
    else:
        raise ValueError(
            f'memo_kind must be "str_hash" or "pickle", given {memo_kind}'
        )

    tree_info = GroupTreeInfo(logwriter=logwriter, memo_factory=memo_factory)

    return Group(tree_info, str(prefix), ())


def _create_default_logwriter(loglevel):
    if term_is_jupyter():
        return HTMLJupyterWriter(loglevel, os.getcwd())
    elif sys.stderr.isatty():
        return ColorTextWriter(sys.stderr, loglevel)
    else:
        return TextWriter(sys.stderr, loglevel)


def _create_logwriter(f, loglevel):
    if isinstance(f, (str, os.PathLike)):
        fname = str(Path(f))
        if fname[-5:] == ".html":
            return HTMLFileWriterOpenOnDemand(loglevel, fname)
        else:
            return TextFileWriterOpenOnDemand(loglevel, fname)

    if isinstance(f, Logger):
        return LoggerWriter(f)

    if hasattr(f, "write") and callable(f.write):
        try:
            if f.isatty():
                return ColorTextWriter(f, loglevel)
        except:
            pass

        return TextWriter(f, loglevel)

    raise TypeError(
        "Logging target must be either str (file name), os.PathLike, "
        "logging.Logger, or and object with `write` method. "
        f"Given {f}"
    )


def _get_memo_factory_pickle(pickle_key):
    if type(pickle_key) == str:
        try:
            pickle_key = bytes.fromhex(pickle_key)
        except ValueError as e:
            raise ValueError(
                "If given as str, pickle_key must be a hexadecimal string"
            ) from e
    elif type(pickle_key) != bytes:
        raise TypeError("pickle_key must be bytes or hexadecimal str")

    def _memo_factory_pickle(args):
        return PickleMemo(args, pickle_key)

    return _memo_factory_pickle


def _memo_factory_str_hash(args):
    return StrHashMemo(args)

