from __future__ import annotations
import os, inspect, time
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
    overload,
    Sequence,
    List,
    TypeVar,
    Collection,
    Container,
)
from typing_extensions import Self, TypeGuard, TypeAlias, ParamSpec

from ..core.make import MakeSummary

from ..utils.frozen_dict import FrozenDict
from ..utils.nest import map_structure_with_set
from .atom import Atom
from ..rule.file import File, IFile
from .core import IRule, GroupTreeInfo, IGroup, concat_prefix, require_tree_init, make

StrOrPath: TypeAlias = "Union[str, PathLike[str]]"

K = TypeVar("K", bound=str)
P = ParamSpec("P")
T = TypeVar("T")


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


class Rule(IRule, Generic[K]):
    _raw_rule_id: int
    _info: GroupTreeInfo
    _name: Tuple[str]
    _files: FrozenDict[K, IFile]
    _xfiles: Sequence[str]
    _file_keys_hint: Optional[List[K]]
    _file_keys: List[K]
    _parent: IGroup

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
    ):
        self._init_main(yfiles, method, args, kwargs)
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
    ) -> Self:
        self._info = group_tree_info
        self._name = name
        self._file_keys_hint = None
        self._parent = parent
        self._file_keys = []  # do not read before the rule is fully initialized
        self._init_main(yfiles, method, args, kwargs)

        return self

    @property
    def initialized(self) -> bool:
        return self._name in self._info.rules_to_be_init

    @require_tree_init
    def __getattr__(self, key: K) -> IFile:
        return self.__getitem__(key)

    @require_tree_init
    def __getitem__(self, key: Union[int, K]) -> IFile:
        if isinstance(key, int):
            return self._files[self._file_keys[key]]
        else:
            return self._files[key]

    @property
    def parent(self) -> IGroup:
        return self._parent

    def touch(
        self,
        file: bool = True,
        memo: bool = True,
        create: bool = True,
        t: Union[float, None] = None,
    ) -> None:
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
            self._info.rule_store.rules[self.raw_rule_id].update_memo()

    def clean(self) -> None:
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
    ):
        if self.initialized:
            raise RuntimeError("Already initialized")

        args_ = (args, kwargs)

        # Add path prefix
        yfiles = {
            k: f.copy_with(_normalize_path(str(f), self._parent.prefix))
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
        method_args, method_kwargs = _replace_Atom_and_IFile(  # type: ignore
            args_
        )

        # Validate method signature
        if not callable(method):
            raise TypeError(f"method must be callable. Given {method}")

        _assert_signature_match(method, method_args, method_kwargs)

        # Create memo
        memo = self._info.memo_factory(args_)

        # Update the RuleStore (create and add a new raw Rule)
        raw_rule = self._info.rule_store.add(
            yp2f, xp2f, method, method_args, method_kwargs, memo, self._name
        )

        self._info.rules_to_be_init.remove(self._name)

        # Update self
        self._raw_rule_id = raw_rule.id
        self._files = FrozenDict(yfiles)
        self._xfiles = list(xp2f)
        self._file_keys = list(yfiles)

    @overload
    def init(
        self,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[Any]]],
            K,
            PathLike[Any],
        ],
        method: Callable[P, object],
    ) -> Callable[P, None]:
        ...

    @overload
    def init(
        self,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[Any]]],
            K,
            PathLike[Any],
        ],
    ) -> Callable[[Callable[[], object]], None]:
        ...

    def init(
        self,
        output_files: object,
        method: object = None,
    ) -> Callable[..., None]:
        if self.initialized:
            raise RuntimeError("Already initialized")

        yfiles = parse_args_output_files(
            self._file_keys_hint, output_files, File
        )

        if method is None:

            def _deco(method: object):
                args, kwargs = Rule_init_parse_deco_func(method)
                self.__init_full__(yfiles, method, args, kwargs)

            return _deco
        else:

            def _init(*args: object, **kwargs: object):
                self.__init_full__(yfiles, method, args, kwargs)

            return _init

    def _get_info(self) -> GroupTreeInfo:
        return self._info

    @property
    @require_tree_init
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
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    @property
    @require_tree_init
    def files(self) -> Mapping[K, IFile]:
        return self._files


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


def parse_args_output_files(
    keys: Optional[Sequence[K]],
    output_files: object,
    IFile_factory: Callable[[StrOrPath], IFile],
) -> Dict[K, IFile]:
    if isinstance(output_files, (tuple, list)):
        outs: Dict[str, object] = {
            str(v): v
            for v in output_files  # pyright: ignore [reportUnknownVariableType]
        }
    elif isinstance(output_files, (str, os.PathLike)):
        outs = {str(output_files): output_files}
    elif isinstance(output_files, Mapping):
        outs = dict(output_files)
    else:
        raise TypeError(
            "output_files must be str | PathLike | Sequence[str|PathLike] "
            "| Mapping[str|PathLike]."
        )

    def _to_IFile(f: object) -> IFile:
        if isinstance(f, IFile):
            return f

        if isinstance(f, (str, os.PathLike)):
            return IFile_factory(f)

        raise TypeError(f"Output file must be str or PathLike. Given {f}")

    outs_ = {k: _to_IFile(v) for k, v in outs.items()}

    if not _check_file_keys(outs_, keys):
        raise TypeError(
            f"Runtime type check error: Expected file keys: {keys}, "
            f"Actual keys of given output files: {list(outs_.keys())}"
        )

    return outs_


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
    memo_store: Mapping[int, Atom], args: object
) -> object:
    def _rec(o: object) -> object:
        if id(o) in memo_store:
            return memo_store[id(o)]
        elif isinstance(o, dict):
            return {
                k: _rec(v)
                for k, v in o.items()  # pyright: ignore [reportUnknownVariableType]
            }
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

    return map_structure_with_set(repl, args)


def _assert_all_yfiles_used_in_args(ypaths: Collection[str], args: object):
    unused = set(ypaths)

    def check(v: object):
        if isinstance(v, IFile):
            absp = os.path.abspath((v))
            if absp in unused:
                unused.remove(absp)

    map_structure_with_set(check, args)

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
            absp = os.path.abspath(v)
            if absp not in ypaths:
                res[absp] = v

    map_structure_with_set(check, args)

    return res


def _replace_Atom_and_IFile(args: object) -> object:
    def repl(v: object):
        if isinstance(v, Atom):
            return v.value
        elif isinstance(v, IFile):
            return Path(v)
        else:
            return v

    return map_structure_with_set(repl, args)


def _assert_signature_match(
    func: Callable[..., object],
    args: Sequence[object],
    kwargs: Dict[str, object],
):
    try:
        inspect.signature(func).bind(*args, **kwargs)
    except Exception as e:
        raise TypeError(
            f"Signature of the method does not match the arguments"
        ) from e
