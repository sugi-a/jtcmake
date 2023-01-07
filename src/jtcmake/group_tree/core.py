from __future__ import annotations

import itertools
import os
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import (
    Callable,
    Collection,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    final,
    overload,
)

from typing_extensions import Concatenate, ParamSpec

from ..core.abc import IEvent
from ..core.make import MakeSummary
from ..core.make import make as _make
from ..core.make_mp import make_mp_spawn
from ..logwriter import IWriter
from ..raw_rule import IMemo
from ..raw_rule import Rule as _RawRule
from ..utils.strpath import StrOrPath, fspath2str
from .atom import IAtom
from .event_logger import INoArgFunc, log_make_event


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

    def __repr__(self) -> str:
        return f"{type(self)}(name={self.name})"


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
        """
        Set the path prefix of this group.

        Args:
            dirname: if specified, prefix will be ``dirname + "/"``
            prefix: path prefix.

        You must specify either but not both of ``dirname`` or ``prefix``.

        ``self.set_prefix("a")`` is equivalent to
        ``self.set_prefix(prefix="a/")``.

        If this group is not the root group and the given prefix is a
        relative path, the path prefix of the parent group will be added to
        its start. Absolute paths do not undergo this prefixing.

        Note:
            This method may be called only when the prefix is not yet
            determined. i.e. You may NOT call this method whenever,

            * You have created this group as a root group
            * You have once called it
            * You have once read :attr:`self.prefix <.prefix>`:
              reading :attr:`self.prefix <.prefix>` internally finalizes
              the prefix to ``"{name of this group}/"``
            * You have once read the prefix of a child group:
              reading a child's prefix internally reads the parent's prefix
            * You have initialized any rule in the sub-tree:
              initializing a rule internally reads its parent's prefix

        Example:

            .. testcode::

                # (For Unix only)

                from jtcmake import UntypedGroup

                g = UntypedGroup("root")

                g.add_group("foo").set_prefix("foo-dir")  # dirname
                g.add_group("bar").set_prefix(prefix="bar-")  # prefix
                g.add_group("baz").set_prefix("/tmp/baz")  # dirname abspath
                g.add_group("qux")  # no explicit setting

                assert g.prefix == "root/"
                assert g.foo.prefix == "root/foo-dir/"
                assert g.bar.prefix == "root/bar-"
                assert g.baz.prefix == "/tmp/baz/"
                assert g.qux.prefix == "root/qux/"
        """
        if self.__prefix is not None:
            raise Exception(
                f'Prefix is already set (to "{self.__prefix}"). '
                "This method may be called only when the prefix is not yet "
                "determined. i.e. You may NOT call this method whenever,\n"
                "* You have created this group as a root group\n"
                "* You have once called it\n"
                "* You have once read `self.prefix`\n"
                "  * reading `self.prefix` internally finalizes the prefix\n"
                "* You have once read the prefix of a child group\n"
                "  * it internally reference the parent's prefix\n"
                "* You have initialized any rule in the sub-tree\n"
                "  * initializing a rule internally reads its parent's prefix"
            )

        p = parse_args_prefix(dirname, prefix)

        if self.parent == self:
            self.__prefix = p
        else:
            self.__prefix = concat_prefix(p, self.parent.prefix)

        return self

    @property
    @final
    def prefix(self) -> str:
        """
        Path prefix of this group.

        Seealso:
            :func:`set_prefix`
        """
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
        """
        Readonly dictionary of child groups.

        * Key: base name of the child group
        * Value: child group node object
        """
        ...

    @property
    @abstractmethod
    def rules(self) -> Mapping[str, IRule]:
        """
        Readonly dictionary of child rules.

        * Key: base name of the child rule
        * Value: child rule node object
        """
        ...


class IRule(INode, metaclass=ABCMeta):
    @property
    @abstractmethod
    def raw_rule_id(self) -> int:
        ...

    @property
    @abstractmethod
    def files(self) -> Mapping[str, IFile]:
        """
        Readonly dictionary of output files.

        * Key: file key of the file
        * Value: :class:`jtcmake.IFile` object
        """
        ...

    @property
    @abstractmethod
    def xfiles(self) -> Collection[str]:
        """
        List of path of the input files.
        """
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
        "dirtree",
    )

    rules: List[_RawRule[int, INoArgFunc]]
    ypath2idx: Dict[str, int]
    idx2xpaths: Dict[int, Sequence[str]]
    path2file: Dict[str, IFile]
    idx2name: Dict[int, Tuple[str, ...]]
    dirtree: DirTree

    def __init__(self):
        self.rules = []
        self.ypath2idx = {}
        self.idx2xpaths = {}
        self.path2file = {}
        self.idx2name = {}
        self.dirtree = DirTree()

    def add(
        self,
        yp2f: Mapping[str, IFile],  # abspath(str) => IFile
        xp2f: Mapping[str, IFile],  # abspath(str) => IFile
        method: INoArgFunc,
        memo: IMemo,
        name: Tuple[str, ...],
    ) -> _RawRule[int, INoArgFunc]:
        # Check duplicated registration of yfiles
        for p, f in yp2f.items():
            if p in self.ypath2idx:
                raise ValueError(
                    f"File {f} is already used as an output of another rule"
                )

            self.dirtree.assert_no_collision(Path(f).parts, True)

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

        for f in yp2f.values():
            self.dirtree.add(Path(f).parts, True)

        return rule


class DirTree(Mapping[str, object]):
    trie: dict[str, DirTree | None]

    def __init__(self) -> None:
        self.trie = {}

    def __getitem__(self, __key: str) -> DirTree | None:
        return self.trie[__key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.trie)

    def __len__(self) -> int:
        return len(self.trie)

    def assert_no_collision(
        self, parts: tuple[str, ...], is_file: bool, depth: int = 0
    ):
        trie = self.trie

        if len(parts) <= depth:
            return

        p0 = parts[depth]

        if len(parts) == 1 and is_file:
            if trie.get(p0) is not None:
                raise Exception(
                    f"Directory-vs-File collision was detected. "
                    f"You tried to register a file {Path(*parts)}, "
                    f"but it is already registered as a directory."
                )
        elif p0 in trie:
            child = trie[p0]

            if child is None:
                raise Exception(
                    f"Directory-vs-File collision was detected. "
                    f"You tried to register a path {Path(*parts)}, but "
                    f"{Path(*parts[: depth + 1])} is already registered "
                    f"as a file. "
                )
            else:
                child.assert_no_collision(parts, is_file, depth + 1)

    def add(self, parts: tuple[str, ...], is_file: bool, depth: int = 0):
        trie = self.trie

        if len(parts) <= depth:
            return

        p0 = parts[depth]

        if len(parts) == 1 and is_file:
            if p0 not in trie:
                trie[p0] = None

            return

        if p0 in trie:
            child = trie[p0]
            assert child is not None
        else:
            child = trie[p0] = DirTree()

        child.add(parts, is_file, depth + 1)


class GroupTreeInfo:
    __slots__ = (
        "rule_store",
        "logwriter",
        "memo_factory",
        "memo_store",
        "rules_to_be_init",
        "root",
    )

    rule_store: RuleStore
    logwriter: IWriter
    memo_factory: Callable[[Path, object], IMemo]
    memo_store: Dict[int, IAtom]
    rules_to_be_init: Set[Tuple[str, ...]]
    root: IGroup

    def __init__(
        self,
        logwriter: IWriter,
        memo_factory: Callable[[Path, object], IMemo],
        root: IGroup,
    ):
        self.logwriter = logwriter
        self.memo_factory = memo_factory
        self.memo_store = {}
        self.rule_store = RuleStore()
        self.rules_to_be_init = set()
        self.root = root


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

    _method.__annotations__ = method.__annotations__
    _method.__doc__ = method.__doc__

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

    Warning:

        Safely and effectively using njobs >= 2 require a certain level of
        understanding of Python's threading and multiprocessing and their
        complications.

        Only *inter-process transferable* rules are executed on child processes.
        Other rules are executed on threads of the main process, thus
        subject to the constraints of global interpreter lock (GIL).

        *inter-process transferable* means being able to be sent to a child
        process without errors.

        Child processes are started by the 'spawn' method, not 'fork',
        even on Linux systems.

        njobs >= 2 may not work on interactive interpreters.
        It should work on Jupyter Notebook/Lab but any function or class
        that are defined on the notebook is not inter-process transferable.
    """
    if len(rule_or_groups) == 0:
        return MakeSummary(
            total=0, update=0, skip=0, fail=0, discard=0, detail={}
        )

    for node in rule_or_groups:
        if not isinstance(
            node, (IGroup, IRule)
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("Invalid node {node}")

    info = get_group_info_of_nodes(rule_or_groups)

    ids = gather_raw_rule_ids(rule_or_groups)

    def callback_(event: IEvent[_RawRule[int, INoArgFunc]]):
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
