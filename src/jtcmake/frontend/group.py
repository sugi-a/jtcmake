from __future__ import annotations
from typing import Union, Optional, Sequence, Any
from abc import abstractmethod
import sys, os, pathlib, re, abc, contextlib, collections, time, json, inspect
import itertools
from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path

from .rule import Rule
from .file import File, VFile, IFile, IVFile
from .event_logger import create_event_callback
from ..core.make import make as _make, make_multi_thread, Event
from ..logwriter.writer import \
    TextWriter, ColorTextWriter, HTMLWriter, HTMLJupyterWriter, \
    term_is_jupyter

#from ..writer.writer import get_default_writer, HTMLWriter, Writer
#from . import logger
from ..utils.nest import \
    StructKey, map_structure, flatten, struct_get, \
    flatten_to_struct_keys, pack_sequence_as

#_default_writer = get_default_writer()


class IFileCell:
    @property
    @abstractmethod
    def path(self) -> Any: ...

    @abstractmethod
    def touch(self, _t: Optional[float]): ...

    @abstractmethod
    def clean(self): ...


class FileCellAtom(IFileCell):
    def __init__(self, file):
        assert isinstance(file, IFile)
        self._file = file

    @property
    def path(self) -> Path:
        return self._file.path

    def touch(self, _t=None):
        if _t is None:
            _t = time.time()
        open(self._file.path, 'w').close()
        os.utime(self._file.path, (_t, _t))

    def clean(self):
        try:
            os.remove(self._file.path)
            # TODO: logging
        except:
            pass


class FileCellTuple(tuple, IFileCell):
    def __new__(
        cls,
        lst: Sequence[Union[FileCellAtom, FileCellTuple, FileCellDict]]
    ):
        return super().__new__(cls, lst)

    def __init__(self, lst): ...

    @property
    def path(self) -> Sequence[Any]:
        return tuple(x.path for x in self)

    def touch(self, _t=None):
        if _t is None:
            _t = time.time()
        for x in self: x.touch(_t)

    def clean(self):
        for x in self: x.clean()


class FileCellDict(Mapping, IFileCell):
    def __init__(
        self,
        dic: dict[Any, Union[FileCellAtom, FileCellTuple, FileCellDict]]
    ):
        self._dic = dic

    @property
    def path(self) -> dict[Any, Any]:
        return {k: v.path for k,v in self._dic.items()}

    def touch(self, _t):
        if _t is None: _t = time.time()
        for k,v in self._dic.items(): v.touch(_t)

    def clean(self):
        for k,v in self._dic.items(): v.clean()

    def __getitem__(self, k):
        return self._dic[k]

    def __iter__(self):
        return self._dic.__iter__()

    def __len__(self):
        return len(self._dic)


class RuleCellBase:
    def __init__(self, rule: IRule):
        self._rule = rule

    def make(
        self,
        dry_run=False,
        keep_going=False,
        *,
        logfile=None,
        loglevel=None,
        nthreads=1
    ):
        make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            logfile=logfile,
            loglevel=loglevel,
            nthreads=nthreads
        )


class RuleCellAtom(RuleCellBase, FileCellAtom):
    def __init__(self, rule: IRule, file: IFile):
        RuleCellBase.__init__(self, rule)
        FileCellAtom.__init__(self, file)


class RuleCellTuple(RuleCellBase, FileCellTuple):
    def __new__(cls, rule, lst):
        return FileCellTuple.__new__(cls, lst)

    def __init__(
        self,
        rule: IRule,
        lst: Sequence[Union[FileCellAtom, FileCellTuple, FileCellDict]]
    ):
        RuleCellBase.__init__(self, rule)
        FileCellTuple.__init__(self, lst)


class RuleCellDict(RuleCellBase, FileCellDict):
    def __new__(cls, rule, dic):
        return FileCellDict.__new__(cls, dic)

    def __init__(
        self,
        rule: IRule,
        dic: dict[Any, Union[FileCellAtom, FileCellTuple, FileCellDict]]
    ):
        RuleCellBase.__init__(self, rule)
        FileCellDict.__init__(self, dic)
        

class GroupTreeInfo:
    def __init__(self):
        self.path_to_rule: dict[str, IRule] = {}
        self.path_to_file: dict[str, IFile] = {}


class Group:
    def __init__(
        self,
        info: GroupTreeInfo,
        prefix: str,
        name: Sequence[str]
    ):
        if not isinstance(prefix, str):
            raise TypeError('prefix must be str')

        self._info = info
        self._prefix = prefix
        self._name = name
        self._children: \
            dict[str, Union[Group, RuleCellAtom, RuleCellTuple, RuleCellDict]]\
            = {}


    def add_group(
        self,
        name: str,
        dirname: Optional[str] = None,
        *,
        prefix: Optional[str] = None
    ):
        """
        Call signatures:
            add_group(name, [dirname])
            add_group(name, prefix=prefix)
        """
        if not isinstance(name, (str, os.PathLike)):
            raise TypeError('name must be str or os.PathLike')

        if name in self._children:
            raise KeyError(f'name {repr(name)} already exists in this Group')

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
        logfile=None,
        loglevel=None,
        nthreads=1
    ):
        # TODO: logging
        make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            logfile=logfile,
            loglevel=loglevel,
            nthreads=nthreads
        )


    # APIs
    def add(self, name: str, *args, **kwargs):
        """
        Call signatures:
            add(name, [path], method, *args, **kwargs)
            add(name, [path], None, *args, **kwargs)
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
                return self._add(name, path, method, *args, **kwargs)
            
            return adder

        return self._add(name, path, method, *args, **kwargs)


    def addvf(self, name, *args, **kwargs):
        """Append a VFile (Value File) as a child of this group
        Call signatures:
            addvf(name, method, *args, **kwargs)
            addvf(name, path, method, *args, **kwargs)
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
                return self.add_vf(name, path, method, *args, **kwargs)
            
            return adder

        def wrap_by_VFile(p: Union[str, os.PathLike, IFile]) -> IFile:
            if isinstance(p, (str, os.PathLike)):
                return VFile(p)
            else:
                return p

        path = map_structure(wrap_by_VFile, path)
            
        return self._add(name, path, method, *args, **kwargs)


    def _add(self, name: str, files, method, *args, **kwargs):
        assert isinstance(name, str)
        assert callable(method)

        path_to_rule = self._info.path_to_rule
        path_to_file = self._info.path_to_file

        if name in self._children:
            raise KeyError(f'name `{name}` already exists')

        if name == '':
            raise ValueError(f'name must not be ""')

        # wrap str/os.PathLike in yfiles by File
        def wrap_by_File(p: Union[str, os.PathLike, IFile]) -> IFile:
            if isinstance(p, (str, os.PathLike)):
                return File(p)
            else:
                assert isinstance(p, IFile)
                return p

        files = map_structure(wrap_by_File, files)

        # add prefix to paths of yfiles if necessary 
        def add_pfx(f: IFile):
            if os.path.isabs(f.path):
                return f
            else:
                return f.__class__(self._prefix + str(f.path))
                # TODO: __init__ of f's class may take args other than path

        files = map_structure(add_pfx, files)

        # expand SELFs in args
        _expanded = False
        def expand_self(arg: Any):
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
                
        # Unwrap FileCellAtom
        args_ = [x._file if isinstance(x, FileCellAtom) else x for x in args_]

        # normalize paths
        _norm = lambda f: \
            f.__class__(os.path.abspath(f.path)) if isinstance(f, IFile) else f
        files_ = list(map(_norm, files_))
        args_ = list(map(_norm, args_))

        # check IFile consistency
        p2f = {}
        for x in args_:
            if isinstance(x, IFile):
                if \
                    (x.path in p2f and p2f[x.path] != x) or \
                    (x.path in path_to_file and path_to_file[x.path] != x):
                    raise TypeError(
                        f'Inconsistency in IFiles of path {x.path}: '
                        f'One is {x} and the other is {p2f[x.path]}'
                    )
                else:
                    p2f[x.path] = x

        # check duplicate registration of output files
        for f in files_:
            if f.path in path_to_rule:
                raise ValueError(
                    f'path {f.path} is already used by another rule: '
                    f'{path_to_rule[f.path]}'
                )

        # check if all the y files are included in the arguments
        unused = set(files_) - {f for f in args_ if isinstance(f, IFile)}
        if len(unused) != 0:
            raise ValueError(
                f'Some files are not passed to the method: '
                f'{list(unused_ofiles)}'
            )
        
        # create deplist
        deplist = []
        _added = set()
        for f in args_:
            if isinstance(f, IFile) and path_to_rule.get(f.path) is not None:
                if path_to_rule[f.path] not in _added:
                    deplist.append(path_to_rule[f.path])
                    _added.add(path_to_rule[f.path])

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

        # check if keys for IVFiles are JSON convertible
        def _assert_key_json_convertible(key, f):
            try:
                json.dumps(key)
            except Exception as e:
                raise Exception(
                    f'keys to identify the location of VFile {f.path} '
                    f'contains an element not convertible to JSON: {key}'
                ) from e
            
        for struct_key, f in xfiles:
            if isinstance(f, IVFile):
                for k in struct_key:
                    _assert_key_json_convertible(k, f)

        # create method args
        def _shorter_path(absp):
            cwd = os.getcwd()
            try:
                rel = Path(os.path.relpath(absp, cwd))
                return rel if len(str(rel)) < len(str(absp)) else absp
            except:
                return absp

        method_args_ = [
            _shorter_path(f.path) if isinstance(f, IFile) else f for f in args_
        ]
        method_args, method_kwargs = \
            pack_sequence_as((args, kwargs), method_args_)

        # create Rule
        r = Rule(
            '/'.join((*self._name, name)),
            files_, xfiles, deplist,
            method, method_args, method_kwargs
        )

        # create RuleCell
        files = pack_sequence_as(files, files_)

        def conv_to_atom(x):
            assert isinstance(x, IFile)
            return FileCellAtom(x)
            
        file_cell_root = map_structure(
            conv_to_atom, files,
            seq_factory={list: FileCellTuple, tuple: FileCellTuple},
            map_factory={dict: FileCellDict, Mapping: FileCellDict}
        )

        if isinstance(file_cell_root, FileCellAtom):
            rc = RuleCellAtom(r, file_cell_root._file)
        elif isinstance(file_cell_root, FileCellTuple):
            rc = RuleCellTuple(r, file_cell_root)
        elif isinstance(file_cell_root, FileCellDict):
            rc = RuleCellDict(r, file_cell_root)

        # update group tree
        self._children[name] = rc

        if _ismembername(name):
            self.__dict__[name] = rc

        for f in files_:
            path_to_rule[f.path] = r

        for _k,f in xfiles:
            if f.path not in path_to_rule:
                path_to_rule[f.path] = None

        for f in itertools.chain(files_, (x[1] for x in xfiles)):
            path_to_file[f.path] = f

        return rc


    def clean(self):
        for c in self._children.values():
            c.clean()

    def touch(self, _t: Optional[float]=None):
        if _t is None:
            _t = time.time()
        for c in self._children.values():
            c.touch(_t)

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

def _ismembername(name: str):
    return \
        isinstance(name, str) and \
        name.isidentifier() and \
        name[0] != '_'


def make(
    *rcell_or_groups,
    dry_run=False,
    keep_going=False,
    logfile=None,
    loglevel=None,
    nthreads=1
):
    # create list of unique rules by DFS
    # TODO: raise when multiple group trees are involved
    _added = set()
    rules = []
    stack = list(reversed(rcell_or_groups))

    while stack:
        node = stack.pop()
        if isinstance(node, RuleCellBase):
            if node._rule not in _added:
                rules.append(node._rule)
        else:
            assert isinstance(node, Group)
            stack.extend(node._children.values())

    # TODO: callback
    loglevel = loglevel or 'info'
    base = os.getcwd()

    with contextlib.ExitStack() as s:
        if logfile is not None:
            logf = s.enter_context(open(logfile, 'w'))
            base = os.path.dirname(logfile)

            if logfile[-5:] == '.html':
                writer = s.enter_context(HTMLWriter(logf, loglevel))
            else:
                writer = TextWriter(logf, loglevel)
        elif term_is_jupyter():
            writer = HTMLJupyterWriter(loglevel)
        elif sys.stderr.isatty():
            writer = ColorTextWriter(sys.stderr, loglevel)
        else:
            writer = TextWriter(sys.stderr, loglevel)

        callback = create_event_callback(writer, set(rules), base=base)

        if nthreads <= 1:
            _make(rules, dry_run, keep_going, callback)
        else:
            make_multi_thread(rules, dry_run, keep_going, nthreads, callback)



def create_group(dirname=None, prefix=None):
    if (dirname is None) == (prefix is None):
        raise TypeError('Either dirname or prefix must be specified')

    if dirname is not None:
        assert isinstance(dirname, (str, os.PathLike))
        prefix = str(dirname) + os.path.sep

    assert isinstance(prefix, (str, os.PathLike))

    return Group(GroupTreeInfo(), str(prefix), ())


SELF = StructKey(())
