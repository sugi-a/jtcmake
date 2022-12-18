from __future__ import annotations
import os
import inspect
import time
import re
from pathlib import Path
from os import PathLike
from typing import (
    Any,
    Callable,
    Mapping,
    Optional,
    Tuple,
    Dict,
    Generic,
    Union,
    Sequence,
    List,
    TypeVar,
    Collection,
    Container,
    overload,
)
from typing_extensions import TypeGuard, ParamSpec, Concatenate

from ..raw_rule import IMemo

from ..core.make import MakeSummary

from ..utils.dict_view import DictView
from ..utils.nest import map_structure
from ..utils.strpath import StrOrPath
from .atom import unwrap_real_values
from .file import File, VFile
from .core import (
    IRule,
    GroupTreeInfo,
    IGroup,
    concat_prefix,
    require_tree_init,
    make,
    IFile,
    IAtom,
)
from .event_logger import INoArgFunc
from .fake_path import FakePath
from ..memo import Memo

K = TypeVar("K", bound=str)
P = ParamSpec("P")
T = TypeVar("T")


class _NoArgFunc(INoArgFunc):
    __slots__ = ("_method", "_args", "_kwargs")

    def __init__(
        self,
        method: Callable[..., object],
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
    ) -> None:
        self._method = method
        self._args = args
        self._kwargs = kwargs

    @property
    def method(self) -> Callable[..., object]:
        return self._method

    @property
    def args(self) -> Tuple[object, ...]:
        return self._args

    @property
    def kwargs(self) -> Dict[str, object]:
        return self._kwargs


class SelfRule:
    __slots__ = ["_key"]
    _key: Union[str, int, None]

    def __init__(self, key: Union[None, str, int] = None):
        self._key = key

    def __getitem__(self, key: Union[str, int]) -> SelfRule:
        return SelfRule(key)

    def __getattr__(self, key: str) -> SelfRule:
        return self[key]

    def __repr__(self):
        if self._key is None:
            return self.__class__.__name__
        else:
            return f"{self.__class__.__name__}({self._key})"

    @property
    def key(self) -> Union[None, str, int]:
        return self._key


SELF: Any = SelfRule()

_T_Rule = TypeVar("_T_Rule", bound=IRule)
_T_deco_f = TypeVar("_T_deco_f", bound=Callable[[], object])


def require_init(
    rule_method: Callable[Concatenate[_T_Rule, P], T]
) -> Callable[Concatenate[_T_Rule, P], T]:
    def _method(self: _T_Rule, *args: P.args, **kwargs: P.kwargs) -> T:
        info = self._get_info()  # pyright: ignore [reportPrivateUsage]

        if self.name_tuple in info.rules_to_be_init:
            try:
                method_name = rule_method.__name__
            except AttributeError:
                method_name = "<unknown method>"

            raise Exception(
                f"Rule {self.name} must be initialized "
                f"before calling the method ({method_name})"
            )

        return rule_method(self, *args, **kwargs)

    return _method


class Rule(  # pyright: ignore [reportIncompatibleMethodOverride]
    IRule, IAtom, FakePath, Generic[K]
):
    _raw_rule_id: int
    _info: GroupTreeInfo
    _name: Tuple[str]
    _files: DictView[K, IFile]
    _xfiles: Sequence[str]
    _file_keys_hint: Optional[List[K]]
    _file_keys: List[K]
    _parent: IGroup
    _memo: Memo[object] | None

    def __init_partial__(
        self,
        name: Tuple[str, ...],
        group_tree_info: GroupTreeInfo,
        file_keys_hint: Optional[List[K]],
        parent: IGroup,
    ):
        self._info = group_tree_info
        self._name = name
        self._file_keys_hint = file_keys_hint
        self._parent = parent
        self._file_keys = []  # do not read before the rule is fully initialized

        self._info.rules_to_be_init.add(name)

    def __init_full__(
        self,
        yfiles: Dict[K, IFile],
        method: object,
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
        noskip: bool,
    ):
        if self.initialized:
            raise RuntimeError(f"Rule {self.name} is already initialized")

        self._init_main(yfiles, method, args, kwargs, noskip)
        self._info.rules_to_be_init.remove(self._name)

    def __init_at_once__(
        self,
        name: Tuple[str, ...],
        group_tree_info: GroupTreeInfo,
        parent: IGroup,
        yfiles: Mapping[K, IFile],
        method: object,
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
        noskip: bool,
    ) -> Rule[K]:
        self._info = group_tree_info
        self._name = name
        self._file_keys_hint = None
        self._parent = parent
        self._file_keys = []  # do not read before the rule is fully initialized
        self._init_main(yfiles, method, args, kwargs, noskip)

        return self

    @property
    def initialized(self) -> bool:
        return self._name not in self._info.rules_to_be_init

    def __getattr__(self, key: K) -> IFile:
        """Just for type checkers"""
        raise AttributeError(key)

    def __getitem__(self, key: Union[int, K]) -> IFile:
        if isinstance(key, int):
            return self._files[self._file_keys[key]]
        else:
            return self._files[key]

    @property
    def parent(  # pyright: ignore [reportIncompatibleMethodOverride]
        self,
    ) -> IGroup:
        """Parent group node of this rule."""
        return self._parent

    def touch(  # pyright: ignore [reportIncompatibleMethodOverride]
        self,
        file: bool = True,
        memo: bool = True,
        create: bool = True,
        t: Union[float, None] = None,
    ) -> None:
        """
        Touch (set mtime to now) the output files and force the memo to record
        the current input state.

        Args:
            file (bool):
                if False, the output files won't be touched. Defaults to True.
            memo (bool): if False, the memo won't be modified. Defaults to True.
            create (bool):
                if True, missing files will be created.
                Otherwise, only the existing files will be touched.
                This option has no effect with ``file=False``.
        """
        logwriter = self._info.logwriter

        if t is None:
            t = time.time()

        if file:
            for f in self.files.values():
                if not f.exists():
                    if not create:
                        continue

                    f.touch()

                os.utime(f, (t, t))
                logwriter.info(f"touch {f}")

        if memo:
            self._info.rule_store.rules[self.raw_rule_id].memo.update()

    def clean(self) -> None:
        """
        Delete all the existing files of this rule.
        """
        logwriter = self._info.logwriter

        for f in self.files.values():
            if not f.exists():
                continue

            try:
                f.unlink(missing_ok=False)
            except Exception as e:
                logwriter.warning(f"Failed to remove {f}. {e}")
            else:
                logwriter.info(f"Delete {f}")

    def _init_main(
        self,
        yfiles: Mapping[K, IFile],
        method: object,
        args: object,
        kwargs: object,
        noskip: bool,
    ):
        if len(yfiles) == 0:
            raise ValueError("Rules must have at least one output file.")

        args_ = (args, kwargs)

        # Add path prefix
        yfiles = {
            k: type(f)(_normalize_path(str(f), self._parent.prefix))
            for k, f in yfiles.items()
        }

        # (Abspath of output) => (IFile of output)
        yp2f = {os.path.abspath(f): f for f in yfiles.values()}

        # Replace reserved objects by Atoms
        args_ = _replace_obj_by_atom_in_structure(self._info.memo_store, args_)

        # Replace SELFs
        args_ = _replace_self({k: v for k, v in yfiles.items()}, args_)

        # Assert that all outputs are included in the arguments
        _assert_all_yfiles_used_in_args(yp2f, args_)

        # (Abspath of input) => (IFile of input)
        xp2f = _find_xfiles_in_args(yp2f, args_)

        # Create final method arguments
        method_args, method_kwargs = unwrap_real_values(args_)  # type: ignore

        # Validate method signature
        if not callable(method):
            raise TypeError(f"method must be callable. Given {method}")

        _assert_signature_match(method, method_args, method_kwargs)
        method_ = _NoArgFunc(method, method_args, method_kwargs)

        # Create memo
        if noskip:
            memo = _UnequalMemo()
        else:
            memo = self._info.memo_factory(next(iter(yp2f.values())), args_)

        # Update the RuleStore (create and add a new raw Rule)
        raw_rule = self._info.rule_store.add(
            yp2f, xp2f, method_, memo, self._name
        )

        # Update self
        self._raw_rule_id = raw_rule.id
        self._files = DictView(yfiles)
        self._xfiles = list(xp2f)
        self._file_keys = list(yfiles)

        if isinstance(memo, Memo):
            self._memo = memo

        for k, f in yfiles.items():
            if k.isidentifier() and not hasattr(self, k):
                setattr(self, k, f)

    @overload
    def init(
        self,
        method: Callable[P, None],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[K]]:
        ...

    @overload
    def init(
        self,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[K]]],
            K,
            PathLike[K],
        ],
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[K]]:
        ...

    @overload
    def init(
        self,
        output_files: Optional[
            Union[
                Mapping[K, StrOrPath],
                Sequence[Union[K, PathLike[K]]],
                K,
                PathLike[K],
            ]
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        ...

    def init(
        self,
        output_files: object = None,
        method: object = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[..., object]:
        """
        Create a temporary function to complete initialization of this rule.

        Note:
           This method must be called only for *uninitialized rules* which
           do not have the output files, method, and method's arguments
           assigned to themselvs yet.

           For example, you have to call this method for rules of
           :class:`StaticGroupBase`-like groups while you must not for rules
           owned by :class:`RulesGroup` groups.

        Args:
            output_files:
                if not specified, this rule's name will be used.
                The following three forms are accepted.

                * **Dict** (``{"key1": file1, "key2": file2, ...}``):
                  ``key1``, ``key2``, ... are the *file keys* and ``file1``,
                  ``file2``, ... are the *file paths*.
                * **List** (``[file1, file2, ...]``):
                  equivalent to a dict-form of
                  ``{str(file1): file1, str(file2): file2}``
                * **Atom** (``file``):
                  equivalent to a dict-form of ``{str(file): file}``

                *File keys* must be str. *File paths* may be either str or
                PathLike including :class:`File` and
                :class:`VFile`.
                If a given file path is neither :class:`File` or
                :class:`VFile`, it will be converted to :class:`File` by
                ``File(file_path)``.

            method: function to create the output files

        Returns:
            **rule_initializer**, a temporary function whose signature is the
            same as the given ``method``.
            Calling it as ``rule_adder(*args, **kwargs)`` completes
            initialization of this rule.

            While executing this rule, ``method`` is called as
            ``method(*args, **kwargs)``.


        Hint:

            **Name Reference in File Paths**

            A file path in a dict-form ``output_files`` may contain text
            symbols ``"<R>"`` and ``"<F>"``, which will be replaced with
            the rule's name and the corresponding file key, respectively.

            For example, ``output_files={ "foo": Path("<R>-<F>.txt") }``
            for a rule named "myrule" is equivalent to
            ``output_files={ "foo": Path("myrule-foo.txt") }``.

            In list/atom form of ``output_files``, you may use ``<R>`` too
            but ``<F>`` is not allowed because the file keys are derived
            from the file paths.


            **Path Prefixing**

            If given as a relative path, file paths get transformed by adding
            the parent group's *path prefix* to the head.

            For example, if the parent group's path prefix is
            ``"output_dir/"``, ``output_files`` of ``{ "a": File("a.txt") }``
            will be transformed into ``{ "a": File("out/a.txt") }``.

            You can suppress this conversion by passing the path as an absolute
            path.


            **Rule-initializer and Argument Substitution**

            ``Rule.init(output_files, method)`` returns a temporary function,
            **rule_initializer** and you must further call it with the
            arguments to be eventually passed to ``method`` like::

                g.rule.init(output_files, method)(SELF, foo="bar")


        Examples:
            Basic usage:

            .. testcode::

                from __future__ import annotations
                from pathlib import Path
                from typing import Literal
                from jtcmake import StaticGroupBase, Rule, SELF

                def split_write(text: str, file1: Path, file2: Path):
                    # Write first half of ``text`` to file1 and the rest to file2
                    n = len(text)
                    file1.write_text(text[: n // 2])
                    file2.write_text(text[n // 2: n])


                def cat(dst: Path, *srcs: Path):
                    with dst.open("w") as f:
                        f.writelines(src.read_text() for src in srcs)


                class MyGroup(StaticGroupBase):
                    __globals__ = globals()  # Only for Sphinx's doctest. Not necessary in normal situations.
                    foo: Rule[Literal["a", "b"]]
                    bar: Rule[str]
                    buz: Rule[str]

                    def init(self) -> MyGroup:
                        '''
                        Supplying keys other than "a" and "b" would be marked as
                        a type error by type checkers such as Mypy and Pyright.
                        '''
                        self.foo.init({"a": "a.txt", "b": "b.txt"}, split_write)(
                            "abcd", SELF[0], SELF[1]
                        )

                        '''
                        The list below will be translated into `{"x.txt": "x.txt", "y.txt": "y.txt"}`
                        (and then `{"x.txt": File("out/x.txt"), "y.txt": File("out/y.txt"}`)
                        '''
                        self.bar.init(["x.txt", "y.txt"], split_write)(
                            "efgh", file1=SELF[0], file2=SELF[1]  # you can use keyword args
                        )

                        self.buz.init("w.txt", cat)(
                            SELF, self.foo[0], self.foo[1], self.bar[0], self.bar[1]
                        )

                        return self

                g = MyGroup("out").init()

                g.make()

                assert Path("out/a.txt").read_text() == "ab"
                assert Path("out/b.txt").read_text() == "cd"
                assert Path("out/x.txt").read_text() == "ef"
                assert Path("out/y.txt").read_text() == "gh"
                assert Path("out/w.txt").read_text() == "abcdefgh"

                import shutil; shutil.rmtree("out")  # Cleanup for Sphinx's doctest
        """
        return self._init(output_files, method, File, noskip)

    @overload
    def initvf(
        self, method: Callable[P, None], /, *, noskip: bool = False
    ) -> Callable[P, Rule[K]]:
        ...

    @overload
    def initvf(
        self,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[K]]],
            K,
            PathLike[K],
        ],
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[K]]:
        ...

    @overload
    def initvf(
        self,
        output_files: Optional[
            Mapping[K, StrOrPath] | Sequence[K | PathLike[K]] | K | PathLike[K]
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        ...

    def initvf(
        self,
        output_files: object = None,
        method: object = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[..., object]:
        """
        Create a temporary function to initialize this rule.

        This method is equal to :func:`init` except the default class
        constructor is :class:`VFile` instead of :class:`File`.

        Seealso:
            :func:`init`
        """
        return self._init(output_files, method, VFile, noskip)

    def _init(
        self,
        output_files: object,
        method: object,
        IFile_fact: Callable[[StrOrPath], IFile],
        noskip: bool,
    ) -> Callable[..., object]:
        if method is None:
            if callable(output_files):
                output_files, method = self.name_tuple[-1], output_files
            elif output_files is None:
                output_files = self.name_tuple[-1]

        yfiles = parse_args_output_files(
            self.name_tuple[-1], self._file_keys_hint, output_files, IFile_fact
        )

        if method is None:

            def decorator(method: Callable[[], object]):
                args, kwargs = Rule_init_parse_deco_func(method)
                self.__init_full__(yfiles, method, args, kwargs, noskip)
                return method

            return decorator
        else:

            def rule_initializer(*args: P.args, **kwargs: P.kwargs) -> Rule[K]:
                self.__init_full__(yfiles, method, args, kwargs, noskip)
                return self

            return rule_initializer

    def _get_info(self) -> GroupTreeInfo:
        return self._info

    @property
    @require_init
    def raw_rule_id(self) -> int:
        return self._raw_rule_id

    @require_tree_init
    def make(
        self,
        dry_run: bool = False,
        keep_going: bool = False,
        *,
        njobs: Optional[int] = None,
    ) -> MakeSummary:
        """
        Make this rule and its dependencies

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

        Seealso:
            :func:`jtcmake.make`
        """
        return make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            njobs=njobs,
        )

    @property
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    @property
    @require_init
    def files(self) -> Mapping[K, IFile]:
        return self._files

    @property
    @require_init
    def xfiles(self) -> Collection[str]:
        return self._xfiles

    @property
    def memo_value(self) -> object:
        return self[0].memo_value

    @property
    def real_value(self) -> object:
        return self[0].real_value

    @property
    def memo_file(self) -> Path | None:
        if self._memo is None:
            return None
        else:
            return self._memo.memo_file


class _UnequalMemo(IMemo):
    def compare(self) -> bool:
        return False

    def update(self):
        ...


def Rule_init_parse_deco_func(
    method: object,
) -> Tuple[Tuple[object, ...], Dict[str, object]]:
    if not callable(method):
        raise TypeError(f"method must be callable. Given {method}")

    sig = inspect.signature(method)
    params = sig.parameters

    nodefaults = [
        name
        for name, p in params.items()
        if p.default is inspect.Parameter.empty
    ]

    if len(nodefaults) != 0:
        raise TypeError(
            "All the arguments of the method must have a default value. "
            f"Missing ones are: {nodefaults}"
        )

    for name, p in params.items():
        if p.kind == inspect.Parameter.POSITIONAL_ONLY:
            raise TypeError(
                f"method must not have a positional only argument. "
                f"{name} is a positonal only argument."
            )

    kwargs = {k: v.default for k, v in params.items()}

    return (), kwargs


def _validate_str(s: object, err_msg: str) -> str:
    if not isinstance(s, str):
        raise TypeError(err_msg)

    return s


T_type = TypeVar("T_type")


def _validate_type(tp: Tuple[type[T_type], ...], o: object, msg: str) -> T_type:
    if isinstance(o, tp):
        return o  # pyright: ignore
    else:
        raise TypeError(msg)


def _pathlike_to_str(p: object) -> str:
    if not isinstance(p, (str, os.PathLike)):
        raise TypeError("Expected str or os.PathLike. Got {p}")

    return _validate_str(os.fspath(p), "bytes path is not allowed. ({p})")


def _to_IFile(f: object, IFile_factory: Callable[[StrOrPath], IFile]) -> IFile:
    if isinstance(f, IFile):
        return f

    if isinstance(f, (str, os.PathLike)):
        return IFile_factory(f)

    raise TypeError(f"Output file must be str or PathLike. Given {f}")


def parse_args_output_files(
    rule_name: str,
    key_hints: Optional[Sequence[K]],
    output_files: object,
    IFile_factory: Callable[[StrOrPath], IFile],
) -> Dict[K, IFile]:
    if isinstance(output_files, (tuple, list)):
        output_files_str = map(_pathlike_to_str, output_files)
        output_files_str = (
            _repl_name_ref(p, rule_name, None) for p in output_files_str
        )
        outs: Dict[str, IFile] = {
            v: type(_to_IFile(f, IFile_factory))(v)
            for v, f in zip(  # pyright: ignore [reportUnknownVariableType]
                output_files_str, output_files
            )
        }
    elif isinstance(output_files, (str, os.PathLike)):
        k = _pathlike_to_str(output_files)
        k = _repl_name_ref(k, rule_name, None)
        outs = {k: type(_to_IFile(output_files, IFile_factory))(k)}
    elif isinstance(output_files, Mapping):
        output_files_: Mapping[object, object] = output_files
        keys = [
            _validate_type((str,), k, "file key must be str")
            for k in output_files_
        ]
        files_str = map(_pathlike_to_str, output_files_.values())
        files_str = (
            _repl_name_ref(f, rule_name, k) for k, f in zip(keys, files_str)
        )

        files = (
            type(_to_IFile(f, IFile_factory))(sf)
            for f, sf in zip(output_files_.values(), files_str)
        )

        outs = {k: _to_IFile(f, IFile_factory) for k, f in zip(keys, files)}
    else:
        raise TypeError(
            "output_files must be str | PathLike | Sequence[str|PathLike] "
            f"| Mapping[str|PathLike]. Given {output_files}"
        )

    if not _check_file_keys(outs, key_hints):
        raise TypeError(
            f"Runtime type check error: Expected file keys: {key_hints}, "
            f"Actual keys of given output files: {list(outs.keys())}"
        )

    return outs


def _check_file_keys(
    files: Dict[str, IFile], ref: Optional[Sequence[K]]
) -> TypeGuard[Dict[K, IFile]]:
    if ref is None:
        return True

    return len(files) == len(ref) and all(a == b for a, b in zip(files, ref))


def _normalize_path(p: str, pfx: str) -> str:
    p = concat_prefix(p, pfx)

    try:
        rel = os.path.relpath(p, os.getcwd())
        return rel if len(rel) < len(p) else p
    except Exception:
        return p


def _replace_obj_by_atom_in_structure(
    memo_store: Mapping[int, IAtom], args: object
) -> object:
    def _rec(o: object) -> object:
        if id(o) in memo_store:
            return memo_store[id(o)]
        elif isinstance(o, dict):
            _o: Dict[object, object] = o
            return {k: _rec(v) for k, v in _o.items()}
        elif isinstance(o, tuple):
            return tuple(map(_rec, o))
        elif isinstance(o, list):
            return list(map(_rec, o))
        elif isinstance(o, set):
            return set(map(_rec, o))
        else:
            return o

    return _rec(args)


def _replace_self(files: Mapping[str, IFile], args: object) -> object:
    def repl(o: object):
        if isinstance(o, SelfRule):
            if o.key is None:
                if len(files) >= 2:
                    raise TypeError(
                        "Self-without-key is not allowed when the "
                        "rule has multiple output files"
                    )

                return next(iter(files.values()))
            elif isinstance(o.key, int):
                if o.key >= len(files):
                    raise IndexError(
                        f"SELF index is {o.key} but the rule "
                        f"has only {len(files)} output files"
                    )
                return list(files.values())[o.key]
            else:
                if o.key not in files:
                    raise KeyError(f"Failed to resolve SELF: {o.key}")
                return files[o.key]
        else:
            return o

    return map_structure(repl, args)


def _assert_all_yfiles_used_in_args(ypaths: Collection[str], args: object):
    unused = set(ypaths)

    def check(v: object):
        if isinstance(v, IFile):
            absp = os.path.abspath((v))
            if absp in unused:
                unused.remove(absp)

    map_structure(check, args)

    if len(unused) > 0:
        raise ValueError(
            f"All the output files must appear in the method arguments. "
            f"Unused ones are: {unused}"
        )


def _find_xfiles_in_args(
    ypaths: Container[str], args: object
) -> Dict[str, IFile]:
    res: Dict[str, IFile] = {}

    def check(v: object):
        if isinstance(v, IFile):
            f = v
        elif isinstance(v, IRule):
            f = next(iter(v.files.values()))
        else:
            f = None

        if f is not None:
            absp = os.path.abspath(f)
            if absp not in ypaths:
                res[absp] = f

    map_structure(check, args)

    return res


def _assert_signature_match(
    func: Callable[..., object],
    args: Sequence[object],
    kwargs: Dict[str, object],
):
    try:
        inspect.signature(func).bind(*args, **kwargs)
    except Exception as e:
        raise TypeError(
            "Signature of the method does not match the arguments"
        ) from e


NAME_REF_RULE = "<R>"
NAME_REF_FILE = "<F>"


def _repl_name_ref(src: str, rule_name: str, file_key: Optional[str]) -> str:
    def _repl(m: re.Match[str]) -> str:
        r = m.group(0)
        if r == NAME_REF_RULE:
            return rule_name
        else:
            if file_key is None:
                raise ValueError(
                    "File key may not referenced by the output file names "
                    "when the keys weren't explicitly given."
                )

            return file_key

    pattern = f"{re.escape(NAME_REF_RULE)}|{re.escape(NAME_REF_FILE)}"

    a = re.sub(pattern, _repl, src)
    return a
