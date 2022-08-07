from abc import abstractmethod
import sys, os, pathlib, re, abc, contextlib, collections, time, json, inspect, warnings
import itertools
from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path

from ..core.rule import IRule
from .rule import Rule
from .igroup import IGroup
from .file import File, VFile, IFile, IVFile
from . import events as group_events
from .event_logger import create_event_callback
from . import graphviz
from ..core.make import make as _make, make_multi_thread, Event
from ..logwriter.writer import \
    TextWriter, ColorTextWriter, HTMLJupyterWriter, \
    term_is_jupyter, TextFileWriterOpenOnDemand, HTMLFileWriterOpenOnDemand

from ..utils.nest import \
    StructKey, map_structure, flatten, struct_get, \
    flatten_to_struct_keys, pack_sequence_as


class Atom:
    def __init__(self, value, memo_value=lambda x: x):
        """Create Atom: special object that can be placed in args/kwargs
        of Group.add. Atom is used to explicitly indicate an object being
        atom.

        Args:
            value: argument value to be wrapped by Atom
            memo_value: value used for memoization.
                If callable, `memo_value(value)` will be used for memoization
                of this argument. Otherwise, memo_value itself will be used
                for memoization.

        Note:
            You can use it to exclude a lambda function from memoization:
            `g.add('rule.txt', method, Atom(lambda x: x**2, None))`
        """
        self.value = value
        if callable(memo_value):
            self.memo_value = memo_value(value)
        else:
            self.memo_value = memo_value
    
    def __repr__(self):
        v, m = repr(self.value), repr(self.memo_value)
        return f'Atom(value={v}, memo_value={m})'


class IFileNode:
    @property
    @abstractmethod
    def path(self): ...

    @abstractmethod
    def touch(self, _t): ...

    @abstractmethod
    def clean(self): ...


class FileNodeAtom(IFileNode):
    def __init__(self, tree_info, file):
        assert isinstance(file, IFile)
        self._info = tree_info
        self._file = file

    @property
    def path(self):
        return self._file.path

    @property
    def abspath(self):
        return self._file.abspath

    def touch(self, _t=None):
        """Touch this file"""
        if _t is None:
            _t = time.time()
        open(self._file.path, 'w').close()
        os.utime(self._file.path, (_t, _t))
        self._info.callback(group_events.Touch(self.path))

    def clean(self):
        """Delete this file if exists"""
        try:
            os.remove(self._file.path)
            self._info.callback(group_events.Clean(self.path))
        except:
            pass

    def __repr__(self):
        return f'FileNodeAtom("{self.path}")'


class FileNodeTuple(tuple, IFileNode):
    def __new__(cls, lst):
        return super().__new__(cls, lst)

    def __init__(self, lst): ...

    @property
    def path(self):
        return tuple(x.path for x in self)

    @property
    def abspath(self):
        return tuple(x.abspath for x in self)

    def touch(self, _t=None):
        """Touch files in this tuple"""
        if _t is None:
            _t = time.time()
        for x in self: x.touch(_t)

    def clean(self):
        """Delete files in this tuple"""
        for x in self: x.clean()

    def __repr__(self):
        return f'FileNodeTuple{super().__repr__()}'


class FileNodeDict(Mapping, IFileNode):
    def __init__(self, dic):
        self._dic = dic

    @property
    def path(self):
        return {k: v.path for k,v in self._dic.items()}

    @property
    def abspath(self):
        return {k: v.abspath for k,v in self._dic.items()}

    def touch(self, _t=None):
        """Touch files in this dict"""
        if _t is None:
            _t = time.time()
        for k,v in self._dic.items():
            v.touch(_t)

    def clean(self):
        """Delete files in this dict"""
        for k,v in self._dic.items(): v.clean()

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
        return f'FileNodeDict{dict(self)}'


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
        nthreads=1
    ):
        make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            nthreads=nthreads
        )

    @property
    def name(self):
        return self._name


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
        return f'RuleNodeTuple{tuple(self)}'


class RuleNodeDict(RuleNodeBase, FileNodeDict):
    def __new__(cls, _name, _rule, _group_tree_info, dic):
        return FileNodeDict.__new__(cls)

    def __init__(self, name, rule, group_tree_info, dic):
        RuleNodeBase.__init__(self, name, rule, group_tree_info)
        FileNodeDict.__init__(self, dic)
        
    def __repr__(self):
        return f'RuleNodeDict{dict(self)}'


class GroupTreeInfo:
    def __init__(self, logwriters, pickle_key):
        self.path_to_rule = {}
        self.path_to_file = {}
        self.rule_to_name = {}
        self.pickle_key = pickle_key

        self.callback = create_event_callback(logwriters, self.rule_to_name)

    
class Group(IGroup):
    def __init__(self, info, prefix, name):
        if not isinstance(prefix, str):
            raise TypeError('prefix must be str')

        self._info = info
        self._prefix = prefix
        self._name = name
        self._children = {}


    def add_group(self, name, dirname = None, *, prefix = None):
        """Add a child Group node
        Args:
            name: name of the node. (str|os.PathLike)
            dirname: directory for the node (str|os.PathLike)
            prefix: path prefix for the node (str|os.PathLike)
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
            raise TypeError('name must be str or os.PathLike')

        if name in self._children:
            raise KeyError(f'name {repr(name)} already exists in this Group')

        if not _is_valid_node_name(name):
            raise ValueError(f'name "{name}" contains some illegal characters')

        if name == '':
            raise ValueError(f'name must not be ""')

        if dirname is not None and prefix is not None:
            raise TypeError('Either dirname or prefix can be specified')

        if dirname is None and prefix is None:
            dirname = name

        if dirname is not None:
            assert isinstance(dirname, (str, os.PathLike))
            prefix = str(Path(dirname)) + os.path.sep

        assert isinstance(prefix, (str, os.PathLike))

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
        nthreads=1
    ):
        make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            nthreads=nthreads
        )


    # APIs
    def add(self, name, *args, **kwargs):
        """Add a Rule node into this Group node.
        Call signatures:
            (1) add(name, [output_files], method, *args, **kwargs)
            (2) add(name, [output_files], None, *args, **kwargs)


        Args:
            name: str. Name for the Rule
            output_files:
                Nested structure representing the output files of the Rule.
                A leaf node of the structure may be either str, os.PathLike,
                or IFile (including File and VFile).
            method: Callable. Will be called as method(*args, **kwargs) on update

        Returns (1):
            Rule node (Union[RuleNodeAtom, RuleNodeTuple, RuleNodeDict])

        Returns (2):
            A function (method: Callable) -> RuleNode.
        
        Call signature (2) is for decorator-style adding.
            The following two are equivalent:
            `Group.add(name, output_files, None, *args, **kwargs)(method)`
            `Group.add(name, output_files, method, *args, **kwargs)`

        How Group.add differs from Group.addvf:
            Default IFile type used to wrap the nodes in output_files whose
            type is str or os.PathLike is different.
            - Group.add wraps them by File.
            - Group.addvf wraps them by VFile.
        """
        if not isinstance(name, str):
            raise ValueError(f'name must be str')

        if len(args) == 0:
            raise TypeError('method must be specified')

        if callable(args[0]) or args[0] is None:
            path = str(name)
            method, *args = args
        else:
            if not (len(args) >= 2 and (callable(args[1]) or args[1] is None)):
                raise TypeError('method must be specified')

            path, method, *args = args

        if method is None:
            def adder(method):
                self._add(name, path, method, *args, **kwargs)
                return method
            
            return adder

        return self._add(
            name, path, method, *args, **kwargs)


    def addvf(self, name, *args, **kwargs):
        """Add a Rule node into this Group node.
        Call signatures:
            (1) add(name, [output_files], method, *args, **kwargs)
            (2) add(name, [output_files], None, *args, **kwargs)


        Args:
            name: str. Name for the Rule
            output_files:
                Nested structure representing the output files of the Rule.
                A leaf node of the structure may be either str, os.PathLike,
                or IFile (including File and VFile).
            method: Callable. Will be called as method(*args, **kwargs)

        Returns (1):
            Rule node

        Returns (2):
            A function (method: Callable) -> RuleNode.
        
        Call signature (2) is for decorator-style adding.
            The following two are equivalent:
            `Group.add(name, output_files, None, *args, **kwargs)(method)`
            `Group.add(name, output_files, method, *args, **kwargs)`

        How Group.add differs from Group.addvf:
            Default IFile type used to wrap the nodes in output_files whose
            type is str or os.PathLike is different.
            - Group.add wraps them by File.
            - Group.addvf wraps them by VFile.
        """
        if not isinstance(name, str):
            raise ValueError(f'name must be str')

        if len(args) == 0:
            raise TypeError('method must be specified')

        if callable(args[0]) or args[0] is None:
            path = str(name)
            method, *args = args
        else:
            if not (len(args) >= 2 and (callable(args[1]) or args[1] is None)):
                raise TypeError('method must be specified')

            path, method, *args = args

        if method is None:
            def adder(method):
                assert callable(method)
                self.add_vf(name, path, method, *args, **kwargs)
                return method
            
            return adder

        def wrap_by_VFile(p):
            if isinstance(p, (str, os.PathLike)):
                return VFile(p)
            else:
                return p

        path = map_structure(wrap_by_VFile, path)
            
        return self._add(
            name, path, method, *args, **kwargs)


    def _add(
        self, name, files,
        method, *args, **kwargs
    ):
        assert isinstance(name, str)
        assert callable(method)

        path_to_rule = self._info.path_to_rule
        path_to_file = self._info.path_to_file

        if not _is_valid_node_name(name):
            raise ValueError(f'name "{name}" contains some illegal characters')
        if name in self._children:
            raise KeyError(f'name `{name}` already exists')

        if name == '':
            raise ValueError(f'name must not be ""')

        # wrap str/os.PathLike in yfiles by File
        def wrap_by_File(p):
            if isinstance(p, (str, os.PathLike)):
                return File(p)
            else:
                assert isinstance(p, IFile)
                return p

        files = map_structure(wrap_by_File, files)

        # add prefix to paths of yfiles if necessary 
        def add_pfx(f):
            if os.path.isabs(f.path):
                return f
            else:
                return f.__class__(self._prefix + str(f.path))
                # TODO: __init__ of f's class may take args other than path

        files = map_structure(add_pfx, files)

        # expand SELFs in args
        _expanded = False
        def expand_self(arg):
            nonlocal _expanded
            if isinstance(arg, StructKey):
                _expanded = True
                try:
                    return struct_get(files, arg)
                except:
                    raise ValueError(f'Invalid keys for SELF')
            else:
                return arg

        args, kwargs = map_structure(expand_self, (args, kwargs))

        if not _expanded:
            args = (files, *args)

        # validate method signature
        try:
            inspect.signature(method).bind(*args, **kwargs)
        except Exception as e:
            raise Exception(f'Method signature and args/kwargs do not match') from e

        # flatten yfiles and args (for convenience)
        try:
            files_ = flatten(files)
        except Exception as e:
            raise Exception(
                f'Failed to flatten the input file structure. '
                f'This error occurs when the structure contains a dict '
                f'whose keys are not sortable.'
            ) from e

        try:
            args_ = flatten((args, kwargs))
        except Exception as e:
            raise Exception(
                f'Failed to flatten the structure of the args/kwargs. '
                f'This error occurs when it contain a dict '
                f'whose keys are not sortable.'
            ) from e
        
        if len(files_) == 0:
            raise ValueError('at least 1 output file must be specified')
                
        # Unwrap FileNodeAtom
        args_ = [x._file if isinstance(x, FileNodeAtom) else x for x in args_]

        # normalize paths (take the shorter one of absolute or relative path)
        def _shorter_path(p):
            cwd = os.getcwd()
            try:
                rel = Path(os.path.relpath(p, cwd))
                return rel if len(str(rel)) < len(str(p)) else p
            except:
                return p

        _norm = lambda f: \
            f.__class__(_shorter_path(f.path)) if isinstance(f, IFile) else f
        files_ = list(map(_norm, files_))
        args_ = list(map(_norm, args_))

        # check IFile consistency
        p2f = {}
        for x in args_:
            if isinstance(x, IFile):
                if \
                    (x.path in p2f and p2f[x.path] != x) or \
                    (
                        x.abspath in path_to_file and
                        path_to_file[x.abspath] != x
                    ):
                    raise TypeError(
                        f'Inconsistency in IFiles of path {x.path}: '
                        f'One is {x} and the other is {p2f[x.path]}'
                    )
                else:
                    p2f[x.path] = x

        # check duplicate registration of output files
        for f in files_:
            if f.abspath in path_to_rule:
                raise ValueError(
                    f'path {f.path} is already used by another rule: '
                    f'{path_to_rule[f.abspath]}'
                )

        # check if all the y files are included in the arguments
        unused = set(files_) - {f for f in args_ if isinstance(f, IFile)}
        if len(unused) != 0:
            raise ValueError(
                f'Some files are not passed to the method: '
                f'{list(unused)}'
            )
        
        # create deplist
        deplist = []
        _added = set()
        for f in args_:
            if isinstance(f, IFile) and path_to_rule.get(f.abspath) is not None:
                if path_to_rule[f.abspath] not in _added:
                    deplist.append(path_to_rule[f.abspath])
                    _added.add(path_to_rule[f.abspath])

        # create xfiles
        ypaths = set(f.path for f in files_)
        try:
            arg_keys = flatten_to_struct_keys(args)
        except Exception as e:
            raise Exception(
                f'Failed to flatten keyword arguments. '
                f'This error occurs when args/kwargs contain a dict '
                f'whose keys are not sortable.'
            ) from e

        xfiles = [
            (k,f) for k,f in zip(arg_keys, args_)
            if isinstance(f, IFile) and f.path not in ypaths
        ]

        # check if keys for IVFiles are str/int/float
        for struct_key, f in xfiles:
            if isinstance(f, IVFile):
                for k in struct_key:
                    if not isinstance(k, (str, int, float)):
                        raise TypeError(
                            'keys of dicts in args/kwargs must be either'
                            f'str, int, or float. Given {k}'
                        )

        # create method args
        def _unwrap_IFile_Atom(x):
            if isinstance(x, IFile):
                return x.path
            elif isinstance(x, Atom):
                return x.value
            else:
                return x

        method_args = pack_sequence_as((args, kwargs), args_)
        method_args = map_structure(_unwrap_IFile_Atom, method_args)
        method_args, method_kwargs = method_args

        # create memoization args
        def _repl_IFile_Atom(x):
            if isinstance(x, IFile):
                return None
            elif isinstance(x, Atom):
                return x.memo_value
            else:
                return x

        memo_args = pack_sequence_as((args, kwargs), args_)
        memo_args = map_structure(_repl_IFile_Atom, memo_args)

        # create Rule
        r = Rule(
            files_, xfiles, deplist,
            method, method_args, method_kwargs,
            kwargs_to_be_memoized=memo_args,
            pickle_key=self._info.pickle_key,
        )

        # create RuleNode
        files = pack_sequence_as(files, files_)

        def conv_to_atom(x):
            assert isinstance(x, IFile)
            return FileNodeAtom(self._info, x)
            
        file_node_root = map_structure(
            conv_to_atom, files,
            seq_factory={list: FileNodeTuple, tuple: FileNodeTuple},
            map_factory={dict: FileNodeDict, Mapping: FileNodeDict}
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

        for f in files_:
            path_to_rule[f.abspath] = r

        for _k,f in xfiles:
            if f.abspath not in path_to_rule:
                path_to_rule[f.abspath] = None

        for f in itertools.chain(files_, (x[1] for x in xfiles)):
            path_to_file[f.abspath] = f

        self._info.rule_to_name[r] = '/'.join((*self._name, name))

        return rc


    def clean(self):
        """Delete files under this Group"""
        for c in self._children.values():
            c.clean()

    def touch(self, _t=None):
        """Touch (set the mtime to now) files under this Group"""
        if _t is None:
            _t = time.time()
        for c in self._children.values():
            c.touch(_t)


    def _get_children_names(self, dst, group, rule):
        for k,c in self._children.items():
            if isinstance(c, Group):
                if group:
                    dst.append(c._name)

                c._get_children_names(dst, group, rule)
            else:
                if rule:
                    dst.append((*self._name, k))



    def select(self, pattern):
        if len(pattern) == 0:
            raise ValueError(f'Invalid pattern "{pattern}"')

        is_group = pattern[-1] == '/'

        pattern = pattern.strip('/')
        parts = re.split('/+', pattern)

        SEP = ';'
        regex = []
        for p in parts:
            assert len(p) > 0

            if p.find('**') != -1 and p != '**':
                raise ValueError(
                    'Invalid pattern: "**" can only be an entire component'
                )
            if p == '**':
                regex.append(f'({SEP}[^{SEP}]+)*')
            else:
                if p == '*':
                    # single * does not match an empty str
                    regex.append(f'{SEP}[^{SEP}]+')
                else:
                    def _repl(x):
                        x = x.group()
                        return f'[^{SEP}]*' if x == '*' else re.escape(x)
                    p = re.sub( r'\*|[^*]+', _repl, p)
                    regex.append(f'{SEP}{p}')

        regex = re.compile('^' + ''.join(regex) + '$')
        chnames = [self._name] if is_group else []
        self._get_children_names(chnames, is_group, not is_group)

        res = []
        for name in chnames:
            name = name[len(self._name):]
            if regex.match(''.join(SEP + n for n in name)):
                res.append(struct_get(self, name))
        
        return res


    def __repr__(self):
        name = repr_group_name(self._name)
        return f'<Group name={repr(name)} prefix={repr(self._prefix)}>'

    def __getitem__(self, k):
        return self._children[k]

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)

    def __contains__(self, k):
        return k in self._children


def repr_group_name(group_name):
    return '/' + '/'.join(map(str, group_name))

def repr_rule_name(trg_name):
    return repr_group_name(trg_name[:-1]) + ':' + str(trg_name[-1])

def _ismembername(name):
    return \
        isinstance(name, str) and \
        name.isidentifier() and \
        name[0] != '_'


def _is_valid_node_name(name):
    # Group.select() depends on ':' being invalid
    return not re.search('[;*?"<>|]', name)


def make(
    *rule_or_groups,
    dry_run=False,
    keep_going=False,
    nthreads=1
):
    # create list of unique rules by DFS
    _added = set()
    rules = []
    stack = list(reversed(rule_or_groups))
    _info = None

    while stack:
        node = stack.pop()
        
        if _info is None:
            _info = node._info
        else:
            if _info is not node._info:
                raise ValueError(
                    f'All Groups/Rules must belong to the same Group tree. '
                    f'This rule is to prevent potentially erroneous operations'
                )

        if isinstance(node, RuleNodeBase):
            if node._rule not in _added:
                rules.append(node._rule)
        else:
            assert isinstance(node, Group)
            stack.extend(node._children.values())

    if nthreads <= 1:
        _make(rules, dry_run, keep_going, _info.callback)
    else:
        make_multi_thread(
            rules, dry_run, keep_going, nthreads, _info.callback)



def create_group(
    dirname=None, prefix=None, *,
    loglevel=None, use_default_logger=True, logfile=None,
    pickle_key=None,
):
    """Create a root Group node.
    Args:
        dirname (str|os.PathLike): directory name for this Group node.
        prefix (str|os.PathLike): path prefix for this Group node.
            - Either (but not both) dirname or prefix must be specified.
            - The following two are equivalent:
                1. `create_group(dirname='dir')`
                2. `create_group(prefix='dir/')`
        loglevel ("debug"|"info"|"warning"|"error"|None):
            log level. Defaults to "info"
        use_default_logger (bool): If True, logs will be printed to terminal.
            Defaults to True.
        logfile (str|os.PathLike|tuple[str|os.PathLike]|None):
            If specified, logs are printed to the file(s).
            If the file extension is .html, logs are printed in HTML format.
        pickle_key (bytes|str||None): key used to authenticate pickle data.
            If str, it must be a hexadecimal str, and will be converted to
            bytes by `bytes.fromhex(pickle_key)`.
            If None, the default pickle key will be used. You can configure
            the default by `jtcmake.set_default_pickle_key(key)`

    Returns:
        Group: Root group node
    """
    if (dirname is None) == (prefix is None):
        raise TypeError('Either dirname or prefix must be specified')

    if dirname is not None:
        assert isinstance(dirname, (str, os.PathLike))
        prefix = str(dirname) + os.path.sep

    assert isinstance(prefix, (str, os.PathLike))

    loglevel = loglevel or 'info'

    if logfile is None:
        logfiles = []
    elif isinstance(logfile, (list, tuple)):
        logfiles = logfile
    else:
        assert isinstance(logfile, (str, os.PathLike))
        logfiles = [logfile]

    logwriters = [_create_logwriter(f, loglevel) for f in logfiles]

    if use_default_logger:
        logwriters.append(_create_default_logwriter(loglevel))

    if pickle_key is None:
        pickle_key = _default_pickle_key
    elif type(pickle_key) == str:
        pickle_key = bytes.fromhex(pickle_key)
    elif type(pickle_key) != bytes:
        raise TypeError('pickle_key must be bytes or hexadecimal str')

    if pickle_key == _DEFAULT_PICKLE_KEY:
        warning_ = (
            f'You are using the default pickle key {_DEFAULT_PICKLE_KEY}.\n'
            'For security reasons, it is recommended to provide your own '
            'key by either,\n\n'
            '* jtcmake.set_default_pickle_key(b"your own key"), or\n'
            '* jtcmake.create_group("dir", pickle_key=b"your own key")\n'
            'Pickle key is used to authenticate pickled data.'
        )
        warnings.warn(warning_)

    tree_info = GroupTreeInfo(logwriters=logwriters, pickle_key=pickle_key)

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
        if fname[-5:] == '.html':
            return HTMLFileWriterOpenOnDemand(loglevel, fname)
        else:
            return TextFileWriterOpenOnDemand(loglevel, fname)
    else:
        if not (hasattr(f, 'write') and callable(f.write)):
            raise TypeError(f'{f} is not a writable stream')

        try:
            if f.isatty():
                return ColorTextWriter(f, loglevel)
        except:
            pass

        return TextWriter(f, loglevel)


_DEFAULT_PICKLE_KEY = bytes.fromhex('FFFF')
_default_pickle_key = _DEFAULT_PICKLE_KEY

def set_default_pickle_key(key):
    global _default_pickle_key
    if type(key) == bytes:
        _default_pickle_key = key
    elif type(key) == str:
        _default_pickle_key = bytes.fromhex(key)
    else:
        raise TypeError('key must be bytes or hexadecimal str')


SELF = StructKey(())
