import sys, os, pathlib, re, contextlib, time, json, inspect
import itertools
from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path
from logging import Logger

from ..rule.rule import Rule
from ..rule.memo import PickleMemo, StrHashMemo
from .abc import IGroup, IFileNode
from ..rule.file import File, VFile, IFile, IFileBase
from .event_logger import log_make_event
from ..core.make import make as _make
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


class FileNodeAtom(IFileNode):
    def __init__(self, tree_info, file):
        assert isinstance(file, IFileBase)
        self._info = tree_info
        self._file = file

    @property
    def path(self):
        return self._file.path

    @property
    def abspath(self):
        return self._file.abspath

    def touch(self, create=False, _t=None):
        """Touch this file

        Args:
            create (bool):
                if False (default), skip the file if it does not exist.
            _t (float):
                set mtime to `_t` after touching
        """
        if _t is None:
            _t = time.time()
        if create or os.path.exists(self._file.path):
            open(self._file.path, "w").close()
            os.utime(self._file.path, (_t, _t))
            self._info.logwriter.info(
                "touch ", RichStr(str(self.path), link=str(self.path)), "\n"
            )

    def clean(self):
        """Delete this file if exists"""
        try:
            os.remove(self._file.path)
            self._info.logwriter.info(
                "clean ", RichStr(str(self.path), link=str(self.path)), "\n"
            )
        except:
            pass

    def __repr__(self):
        return f'FileNodeAtom("{self.path}")'


class FileNodeTuple(tuple, IFileNode):
    def __new__(cls, lst):
        return super().__new__(cls, lst)

    def __init__(self, lst):
        ...

    @property
    def path(self):
        return tuple(x.path for x in self)

    @property
    def abspath(self):
        return tuple(x.abspath for x in self)

    def touch(self, create=False, _t=None):
        """Touch files in this tuple

        Args:
            create (bool):
                if False (default), skip the file if it does not exist.
            _t (float):
                set mtime to `_t` after touching
        """
        if _t is None:
            _t = time.time()
        for x in self:
            x.touch(create, _t)

    def clean(self):
        """Delete files in this tuple"""
        for x in self:
            x.clean()

    def __repr__(self):
        return f"FileNodeTuple{super().__repr__()}"


class FileNodeDict(Mapping, IFileNode):
    def __init__(self, dic):
        self._dic = dic

    @property
    def path(self):
        return {k: v.path for k, v in self._dic.items()}

    @property
    def abspath(self):
        return {k: v.abspath for k, v in self._dic.items()}

    def touch(self, create=False, _t=None):
        """Touch files in this dict
        Args:
            create (bool):
                if False (default), skip the file if it does not exist.
            _t (float):
                set mtime to `_t` after touching
        """
        if _t is None:
            _t = time.time()
        for k, v in self._dic.items():
            v.touch(create, _t)

    def clean(self):
        """Delete files in this dict"""
        for k, v in self._dic.items():
            v.clean()

    def __getitem__(self, k):
        return self._dic[k]

    def __iter__(self):
        return self._dic.__iter__()

    def __len__(self):
        return len(self._dic)

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return hash(id(self))

    def __repr__(self):
        return f"FileNodeDict{dict(self)}"


class RuleNodeBase:
    def __init__(self, name, rule, group_tree_info):
        self._rule = rule
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
        self._rule.update_memo()


class RuleNodeAtom(RuleNodeBase, FileNodeAtom):
    def __init__(self, name, rule, group_tree_info, file):
        RuleNodeBase.__init__(self, name, rule, group_tree_info)
        FileNodeAtom.__init__(self, group_tree_info, file)

    def __repr__(self):
        return f'RuleNodeAtom(path="{self.path}")'


class RuleNodeTuple(RuleNodeBase, FileNodeTuple):
    def __new__(cls, _name, _rule, _group_tree_info, lst):
        return FileNodeTuple.__new__(cls, lst)

    def __init__(self, name, rule, group_tree_info, lst):
        RuleNodeBase.__init__(self, name, rule, group_tree_info)
        FileNodeTuple.__init__(self, lst)

    def __repr__(self):
        return f"RuleNodeTuple{tuple(self)}"


class RuleNodeDict(RuleNodeBase, FileNodeDict):
    def __new__(cls, _name, _rule, _group_tree_info, dic):
        return FileNodeDict.__new__(cls)

    def __init__(self, name, rule, group_tree_info, dic):
        RuleNodeBase.__init__(self, name, rule, group_tree_info)
        FileNodeDict.__init__(self, dic)

    def __repr__(self):
        return f"RuleNodeDict{dict(self)}"


class GroupTreeInfo:
    def __init__(self, logwriter, memo_factory):
        self.rules = []  # list<Rule>
        self.rule2idx = {}  # dict<int, int>
        self.path2idx = {}  # dict<str, int>. idx can be -1
        self.idx2outputs = []  # list<list<IFileBase>>
        self.path_to_file = {}
        self.memo_factory = memo_factory

        self.logwriter = logwriter


class Group(IGroup):
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
        self._children = {}

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

        if name in self._children:
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

        self._children[name] = g

        if _ismembername(name):
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
    def add(self, name, *args, **kwargs):
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
        if isinstance(name, os.PathLike):
            name = str(name)
        elif not isinstance(name, str):
            raise ValueError(f"name must be str|os.PathLike")

        if len(args) == 0:
            raise TypeError("method must be specified")

        if callable(args[0]) or args[0] is None:
            path = str(name)
            method, *args = args
        else:
            if not (len(args) >= 2 and (callable(args[1]) or args[1] is None)):
                raise TypeError("method must be specified")

            path, method, *args = args

        if method is None:

            def adder(method):
                self._add(name, path, method, *args, **kwargs)
                return method

            return adder

        return self._add(name, path, method, *args, **kwargs)

    def addvf(self, name, *args, **kwargs):
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
        if isinstance(name, os.PathLike):
            name = str(name)
        elif not isinstance(name, str):
            raise ValueError(f"name must be str|os.PathLike")

        if len(args) == 0:
            raise TypeError("method must be specified")

        if callable(args[0]) or args[0] is None:
            path = str(name)
            method, *args = args
        else:
            if not (len(args) >= 2 and (callable(args[1]) or args[1] is None)):
                raise TypeError("method must be specified")

            path, method, *args = args

        if method is None:

            def adder(method):
                assert callable(method)
                self.addvf(name, path, method, *args, **kwargs)
                return method

            return adder

        def wrap_by_VFile(p):
            if isinstance(p, (str, os.PathLike)):
                return VFile(p)
            else:
                return p

        path = map_structure(wrap_by_VFile, path)

        return self._add(name, path, method, *args, **kwargs)

    def _add(self, name, files, method, *args, **kwargs):
        assert isinstance(name, str)
        assert callable(method)

        path2idx = self._info.path2idx
        path_to_file = self._info.path_to_file

        if not _is_valid_node_name(name):
            raise ValueError(f'name "{name}" contains some illegal characters')
        if name in self._children:
            raise KeyError(f"name `{name}` already exists")

        if name == "":
            raise ValueError(f'name must not be ""')

        # wrap str/os.PathLike in yfiles by File
        def wrap_by_File(p):
            if isinstance(p, (str, os.PathLike)):
                return File(p)
            else:
                assert isinstance(p, IFileBase)
                return p

        files = map_structure(wrap_by_File, files)

        # add prefix to paths of yfiles if necessary
        def add_pfx(f):
            if os.name == "posix":
                p = os.path.expanduser(f.path)
            else:
                p = f.path

            if os.path.isabs(p):
                return f.__class__(p)
            else:
                return f.__class__(self._prefix + str(p))
                # TODO: __init__ of f's class may take args other than path

        files = map_structure(add_pfx, files)

        # expand SELFs in args
        _expanded = False

        def expand_self(arg):
            nonlocal _expanded
            if isinstance(arg, NestKey):
                _expanded = True
                try:
                    return nest_get(files, arg)
                except:
                    raise ValueError(f"Invalid keys for SELF")
            else:
                return arg

        args, kwargs = map_structure(
            expand_self, (args, kwargs), map_factory={(dict, FileNodeDict): dict}
        )

        if not _expanded:
            args = (files, *args)

        # validate method signature
        try:
            inspect.signature(method).bind(*args, **kwargs)
        except Exception as e:
            raise Exception(f"Method signature and args/kwargs do not match") from e

        # flatten yfiles and args (for convenience)
        try:
            files_ = flatten(files)
        except Exception as e:
            raise Exception(
                f"Failed to flatten the input file structure. "
                f"This error occurs when the structure contains a dict "
                f"whose keys are not sortable."
            ) from e

        try:
            args_ = flatten((args, kwargs))
        except Exception as e:
            raise Exception(
                f"Failed to flatten the structure of the args/kwargs. "
                f"This error occurs when it contain a dict "
                f"whose keys are not sortable."
            ) from e

        if len(files_) == 0:
            raise ValueError("at least 1 output file must be specified")

        # Unwrap FileNodeAtom
        args_ = [x._file if isinstance(x, FileNodeAtom) else x for x in args_]

        # normalize paths (take the shorter one of absolute or relative path)
        def _shorter_path(p):
            cwd = os.getcwd()
            try:
                if os.name == "posix":
                    p = os.path.expanduser(p)
                rel = Path(os.path.relpath(p, cwd))
                return rel if len(str(rel)) < len(str(p)) else p
            except:
                return p

        _norm = (
            lambda f: f.copy_with(_shorter_path(f.path))
            if isinstance(f, IFileBase)
            else f
        )
        files_ = list(map(_norm, files_))
        args_ = list(map(_norm, args_))

        # check IFileBase consistency
        p2f = {}
        for x in args_:
            if isinstance(x, IFileBase):
                if (x.path in p2f and p2f[x.path] != x) or (
                    x.abspath in path_to_file and path_to_file[x.abspath] != x
                ):
                    raise TypeError(
                        f"Inconsistency in IFileBases of path {x.path}: "
                        f"One is {x} and the other is {p2f[x.path]}"
                    )
                else:
                    p2f[x.path] = x

        # check duplicate registration of output files
        for f in files_:
            idx = path2idx.get(f.abspath)
            if idx is None:
                pass
            elif idx == -1:
                raise ValueError(f"{f.path} is already used as an original file")
            else:
                raise ValueError(
                    f"{f.path} is already used by another rule: "
                    f"{self._info.rules[path2idx[f.abspath]]}"
                )

        # check if all the y files are included in the arguments
        unused = set(files_) - {f for f in args_ if isinstance(f, IFileBase)}
        if len(unused) != 0:
            raise ValueError(
                f"Some files are not passed to the method: " f"{list(unused)}"
            )

        # create deplist
        deplist = []
        _added = set()
        for f in args_:
            if isinstance(f, IFileBase) and path2idx.get(f.abspath, -1) != -1:
                dep = path2idx[f.abspath]
                if dep not in _added:
                    deplist.append(dep)
                    _added.add(dep)

        # create xfiles
        ypaths = set(f.path for f in files_)

        xfiles = [
            f
            for f in args_
            if isinstance(f, IFileBase) and f.path not in ypaths  # TODO
        ]

        # create method args
        def _unwrap_IFileBase_Atom(x):
            if isinstance(x, IFileBase):
                return x.path
            elif isinstance(x, Atom):
                return x.value
            else:
                return x

        method_args = pack_sequence_as((args, kwargs), args_)
        method_args = map_structure(_unwrap_IFileBase_Atom, method_args)
        method_args, method_kwargs = method_args

        memo_args = pack_sequence_as((args, kwargs), args_)
        memo = self._info.memo_factory(memo_args)

        # create Rule
        r = Rule(
            files_,
            xfiles,
            deplist,
            method,
            method_args,
            method_kwargs,
            memo=memo,
            name=(*self._name, name),
        )

        # create RuleNode
        files = pack_sequence_as(files, files_)

        def conv_to_atom(x):
            assert isinstance(x, IFileBase)
            return FileNodeAtom(self._info, x)

        file_node_root = map_structure(
            conv_to_atom,
            files,
            seq_factory={list: FileNodeTuple, tuple: FileNodeTuple},
            map_factory={dict: FileNodeDict},
        )

        fullname = (*self._name, name)
        if isinstance(file_node_root, FileNodeAtom):
            rc = RuleNodeAtom(fullname, r, self._info, file_node_root._file)
        elif isinstance(file_node_root, FileNodeTuple):
            rc = RuleNodeTuple(fullname, r, self._info, file_node_root)
        elif isinstance(file_node_root, FileNodeDict):
            rc = RuleNodeDict(fullname, r, self._info, file_node_root)

        # update group tree
        self._children[name] = rc

        if _ismembername(name):
            self.__dict__[name] = rc

        rule_idx = len(self._info.rules)
        self._info.rules.append(r)
        self._info.rule2idx[r] = rule_idx
        assert len(self._info.rules) == len(self._info.rule2idx)

        for f in files_:
            path2idx[f.abspath] = rule_idx

        for f in xfiles:
            if f.abspath not in path2idx:
                # Add as an original file
                path2idx[f.abspath] = -1

        for f in itertools.chain(files_, xfiles):
            path_to_file[f.abspath] = f

        return rc

    def clean(self):
        """Delete files under this Group"""
        for c in self._children.values():
            c.clean()

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
        for c in self._children.values():
            c.touch(create, _t)

    def _get_children_names(self, dst, group, rule):
        for k, c in self._children.items():
            if isinstance(c, Group):
                if group:
                    dst.append(c._name)

                c._get_children_names(dst, group, rule)
            else:
                if rule:
                    dst.append((*self._name, k))

    def select(self, pattern, group=False):
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
        if isinstance(pattern, str):
            if len(pattern) == 0:
                raise ValueError(f'Invalid pattern "{pattern}"')

            group = pattern[-1] == "/"
            pattern = pattern.strip("/")
            parts = re.split("/+", pattern)
        elif isinstance(pattern, (tuple, list)):
            if not all(isinstance(v, str) for v in pattern):
                raise TypeError("Pattern sequence items must be str")

            parts = pattern
        else:
            raise TypeError("Pattern must be str or sequence of str")

        SEP = ";"
        regex = []
        for p in parts:
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
        chnames = [self._name] if group else []
        self._get_children_names(chnames, group, not group)

        res = []
        for name in chnames:
            name = name[len(self._name) :]
            if regex.match("".join(SEP + n for n in name)):
                res.append(nest_get(self, name))

        return res

    def __repr__(self):
        name = repr_group_name(self._name)
        return f"<Group name={repr(name)} prefix={repr(self._prefix)}>"

    def __getitem__(self, k):
        return self._children[k]

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)

    def __contains__(self, k):
        return k in self._children


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
    rules = []
    stack = list(reversed(rule_or_groups))
    _info = None

    if len(rule_or_groups) == 0:
        return True

    while stack:
        node = stack.pop()

        if _info is None:
            _info = node._info
        else:
            if _info is not node._info:
                raise ValueError(
                    f"All Groups/Rules must belong to the same Group tree. "
                    f"This rule is to prevent potentially erroneous operations"
                )

        if isinstance(node, RuleNodeBase):
            if node._rule not in _added:
                rules.append(node._rule)
        else:
            assert isinstance(node, Group)
            stack.extend(node._children.values())

    ids = [_info.rule2idx[r] for r in rules]

    def callback_(event):
        log_make_event(_info.logwriter, event)

    if njobs is not None and njobs >= 2:
        return make_mp_spawn(_info.rules, ids, dry_run, keep_going, callback_, njobs)
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
            raise TypeError('pickle_key must be specified when memo_kind is "pickle"')

        memo_factory = _get_memo_factory_pickle(pickle_key)
    elif memo_kind == "str_hash":
        if pickle_key is not None:
            raise TypeError(
                "pickle_key must not be specified for " "str_hash memoization method"
            )
        memo_factory = _memo_factory_str_hash
    else:
        raise ValueError(f'memo_kind must be "str_hash" or "pickle", given {memo_kind}')

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


SELF = NestKey(())
