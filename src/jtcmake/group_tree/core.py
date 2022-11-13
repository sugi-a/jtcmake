from __future__ import annotations
from abc import ABCMeta, abstractmethod
import os
import itertools
from typing import (
    Callable,
    Collection,
    Mapping,
    Optional,
    Tuple,
    TypeVar,
    Dict,
    Union,
    overload,
    Sequence,
    List,
    Set,
    final,
)
from typing_extensions import ParamSpec, Concatenate
from pathlib import Path

from ..raw_rule import Rule as _RawRule, IMemo
from ..core.make import MakeSummary, make as _make
from ..core.make_mp import make_mp_spawn
from ..core.abc import IEvent
from ..logwriter import IWriter
from .event_logger import log_make_event
from ..utils.strpath import StrOrPath, fspath2str
from .atom import IAtom


class INode(metaclass=ABCMeta):
    @property
    @abstractmethod
    def parent(self) -> IGroup:
        ...

    @abstractmethod
    def _get_info(self) -> GroupTreeInfo:
        ...

    @property
    @abstractmethod
    def name_tuple(self) -> Tuple[str, ...]:
        ...

    @property
    def name(self) -> str:
        if len(self.name_tuple) == 0:
            return "/"
        else:
            return "/" + "/".join(self.name_tuple)


T_Self = TypeVar("T_Self", bound="IGroup")


class IGroup(INode, metaclass=ABCMeta):
    __prefix: Union[None, str] = None

    @abstractmethod
    def __init_as_child__(
        self,
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        ...

    @overload
    def set_prefix(
        self: T_Self, dirname: StrOrPath, *, prefix: None = None
    ) -> T_Self:
        ...

    @overload
    def set_prefix(
        self: T_Self, dirname: None = None, *, prefix: StrOrPath
    ) -> T_Self:
        ...

    @final
    def set_prefix(
        self: T_Self, dirname: object = None, *, prefix: object = None
    ) -> T_Self:
        if self.__prefix is not None:
            raise Exception(
                f'Prefix is already set (to "{self.__prefix}") and '
                "may not be overwritten. Make sure to call set_prefix "
                "before initializing child groups and rules. "
            )

        p = parse_args_prefix(dirname, prefix)

        if self.parent == self:
            self.__prefix = p
        else:
            self.__prefix = concat_prefix(p, self.parent.prefix)

        return self

    @final
    @property
    def prefix(self) -> str:
        if self.__prefix is None:
            # Root node must get prefix in __init__
            assert self.parent != self

            self.set_prefix(self.name_tuple[-1])
            assert self.__prefix is not None
            return self.__prefix
        else:
            return self.__prefix

    @property
    @abstractmethod
    def groups(self) -> Mapping[str, IGroup]:
        ...

    @property
    @abstractmethod
    def rules(self) -> Mapping[str, IRule]:
        ...


class IRule(INode, metaclass=ABCMeta):
    @property
    @abstractmethod
    def raw_rule_id(self) -> int:
        ...

    @property
    @abstractmethod
    def files(self) -> Mapping[str, IFile]:
        ...

    @property
    @abstractmethod
    def xfiles(self) -> Collection[str]:
        ...

    @abstractmethod
    def clean(self) -> None:
        ...

    @abstractmethod
    def touch(
        self, file: bool, memo: bool, create: bool, t: Union[float, None]
    ) -> None:
        ...


class IFile(Path, IAtom, metaclass=ABCMeta):
    """
    Abstract base class to represent a file object.
    """

    """
    For implementors of this ABC:
        It is highly recommended not to have variable properties (public or
        private) in the new class because the default implementations of the
        generative methods of Path (absolute(), resolve(), etc) create new
        instance without copying subclasses' variable properties.
    """

    @abstractmethod
    def is_value_file(self) -> bool:
        ...

    def __eq__(self, other: object) -> bool:
        ts, to = type(self), type(other)
        if issubclass(to, ts) or issubclass(ts, to):
            return super().__eq__(other)
        else:
            return False

    @property
    def real_value(self) -> object:
        return Path(self)


class RuleStore:
    __slots__ = (
        "rules",
        "ypath2idx",
        "idx2xpaths",
        "path2file",
        "idx2name",
    )

    rules: List[_RawRule[int]]
    ypath2idx: Dict[str, int]
    idx2xpaths: Dict[int, Sequence[str]]
    path2file: Dict[str, IFile]
    idx2name: Dict[int, Tuple[str, ...]]

    def __init__(self):
        self.rules = []
        self.ypath2idx = {}
        self.idx2xpaths = {}
        self.path2file = {}
        self.idx2name = {}

    def add(
        self,
        yp2f: Mapping[str, IFile],  # abspath(str) => IFile
        xp2f: Mapping[str, IFile],  # abspath(str) => IFile
        method: Callable[..., object],
        method_args: Tuple[object, ...],
        method_kwargs: Dict[str, object],
        memo: IMemo,
        name: Tuple[str, ...],
    ) -> _RawRule[int]:
        # Check duplicated registration of yfiles
        for p, f in yp2f.items():
            if p in self.ypath2idx:
                raise ValueError(
                    f"File {f} is already used as an output of another rule"
                )

        # Check IFile type consistency of xfiles
        for p, f in xp2f.items():
            f_ = self.path2file.get(p)
            if f_ is not None and f_.resolve() != f.resolve():
                raise TypeError(
                    f"IFile inconsistency detected: argument {f} is of type "
                    f"{type(f)} but the file was registered to be created as "
                    f"{type(f_)}"
                )

        # Create Rule
        id = len(self.rules)
        xids = [self.ypath2idx.get(p, -1) for p in xp2f]
        rule = _RawRule(
            yfiles=list(yp2f.values()),
            xfiles=list(xp2f.values()),
            xfile_is_orig=[i == -1 for i in xids],
            xfile_is_vf=[f.is_value_file() for f in xp2f.values()],
            deplist=set(xids) - {-1},
            method=method,
            args=method_args,
            kwargs=method_kwargs,
            memo=memo,
            id=id,
        )

        # Update stores
        self.rules.append(rule)

        for p, f in yp2f.items():
            self.ypath2idx[p] = id
            self.path2file[p] = f

        for p, f in xp2f.items():
            if p not in self.ypath2idx:
                # Add original
                self.ypath2idx[p] = -1
                self.path2file[p] = f

        self.idx2xpaths[id] = list(xp2f)

        self.idx2name[id] = name

        return rule


class GroupTreeInfo:
    __slots__ = (
        "rule_store",
        "logwriter",
        "memo_factory",
        "memo_store",
        "rules_to_be_init",
    )

    rule_store: RuleStore
    logwriter: IWriter
    memo_factory: Callable[[object], IMemo]
    memo_store: Dict[int, IAtom]
    rules_to_be_init: Set[Tuple[str, ...]]

    def __init__(
        self, logwriter: IWriter, memo_factory: Callable[[object], IMemo]
    ):
        self.logwriter = logwriter
        self.memo_factory = memo_factory
        self.memo_store = {}
        self.rule_store = RuleStore()
        self.rules_to_be_init = set()


P = ParamSpec("P")
T = TypeVar("T")
T_INode = TypeVar("T_INode", bound=INode)


def require_tree_init(
    method: Callable[Concatenate[T_INode, P], T]
) -> Callable[Concatenate[T_INode, P], T]:
    def _method(self: T_INode, *args: P.args, **kwargs: P.kwargs) -> T:
        info = self._get_info()  # pyright: ignore [reportPrivateUsage]

        if len(info.rules_to_be_init) != 0:
            top10names = itertools.islice(info.rules_to_be_init, 10)
            top10names = ["/" + "/".join(n) for n in top10names]
            raise RuntimeError(
                "All rules in the group tree must be initialized "
                f"before calling this method. {len(info.rules_to_be_init)} "
                f"rules are not initialized. {len(top10names)} of them are: "
                "\n" + "\n".join(top10names)
            )
        return method(self, *args, **kwargs)

    return _method


def make(
    *rule_or_groups: Union[IGroup, IRule],
    dry_run: bool = False,
    keep_going: bool = False,
    njobs: Optional[int] = None,
) -> MakeSummary:
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
    if len(rule_or_groups) == 0:
        return MakeSummary(total=0, update=0, skip=0, fail=0, discard=0)

    for node in rule_or_groups:
        if not isinstance(
            node, (IGroup, IRule)
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("Invalid node {node}")

    info = get_group_info_of_nodes(rule_or_groups)

    ids = gather_raw_rule_ids(rule_or_groups)

    def callback_(event: IEvent):
        def id2name(i: int) -> str:
            return "/".join(info.rule_store.idx2name[i])

        log_make_event(info.logwriter, event, id2name)

    if njobs is not None and njobs >= 2:
        return make_mp_spawn(
            info.rule_store.rules, ids, dry_run, keep_going, callback_, njobs
        )
    else:
        return _make(info.rule_store.rules, ids, dry_run, keep_going, callback_)


def get_group_info_of_nodes(nodes: Sequence[INode]) -> GroupTreeInfo:
    if len(nodes) == 0:
        raise Exception("Internal error: nodes must not be empty")

    info = nodes[0]._get_info()  # pyright: ignore [reportPrivateUsage]

    for node in nodes:
        _info = node._get_info()  # pyright: ignore [reportPrivateUsage]
        if _info is not info:
            raise ValueError(
                "All Groups/Rules must belong to the same Group tree. "
            )

    return info


def gather_raw_rule_ids(
    group_or_rules: Sequence[Union[IGroup, IRule]]
) -> List[int]:
    ids: List[int] = []
    visited: Set[INode] = set()

    stack = list(reversed(group_or_rules))

    while stack:
        node = stack.pop()
        if node in visited:
            continue

        visited.add(node)

        if isinstance(node, IRule):
            ids.append(node.raw_rule_id)
        else:
            stack.extend(node.groups.values())
            stack.extend(node.rules.values())

    return ids


def parse_args_prefix(dirname: object, prefix: object) -> str:
    if dirname is not None and prefix is not None:
        raise TypeError(
            "Either dirname or prefix, but not both must be specified"
        )

    if dirname is not None:
        if not isinstance(dirname, (str, os.PathLike)):
            raise TypeError("dirname must be str or PathLike")

        prefix_ = fspath2str(dirname) + os.path.sep
    else:
        if prefix is None:
            prefix_ = ""
        elif isinstance(prefix, (str, os.PathLike)):
            prefix_ = fspath2str(prefix)
        else:
            raise TypeError("prefix must be str or PathLike")

    return prefix_


def concat_prefix(base: str, prefix: str) -> str:
    base = os.path.expanduser(base)
    return base if os.path.isabs(base) else prefix + base
