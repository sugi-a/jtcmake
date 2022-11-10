from __future__ import annotations
import inspect
from logging import Logger
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Generic,
    Union,
    Sequence,
    get_origin,
    get_type_hints,
    Callable,
)

from ..memo.str_hash_memo import StrHashMemo

from ..utils.strpath import StrOrPath
from ..utils.dict_view import DictView
from ..logwriter import Loglevel, WritableProtocol
from .core import IGroup, GroupTreeInfo, IRule, parse_args_prefix
from .rule import Rule
from .group_mixins.basic import (
    BasicMixin,
    BasicInitMixin,
    basic_init_create_logwriter,
)
from .group_mixins.dynamic_container import DynamicRuleContainerMixin
from .group_mixins.memo import MemoMixin
from .group_mixins.selector import SelectorMixin


V = TypeVar("V")

class StaticGroupBase(BasicMixin, BasicInitMixin, SelectorMixin, MemoMixin):
    _info: GroupTreeInfo
    _name: Tuple[str, ...]
    _groups: Dict[str, IGroup]
    _rules: Dict[str, Rule[str]]
    _parent: IGroup

    def __init_as_child__(
        self,
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        self._parent = parent
        self._info = info
        self._name = name

        self._groups = {}
        self._rules = {}

        for child_name, type_hint in get_type_hints(type(self)).items():
            fqcname = (*self._name, child_name)

            tp = _get_type(type_hint)

            if tp is None:
                continue

            if tp == Rule:
                # Rule
                r: Rule[str] = Rule.__new__(Rule)
                r.__init_partial__(fqcname, self._info, None, self)
                setattr(self, child_name, r)
                self._rules[child_name] = r
            elif issubclass(tp, IGroup) and not inspect.isabstract(tp):
                # Group
                g = tp.__new__(tp)
                g.__init_as_child__(self._info, self, fqcname)
                setattr(self, child_name, g)
                self._groups[child_name] = g

    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ""
        else:
            return self._name[-1]

    @property
    def namefq(self) -> str:
        return "/".join(self._name)

    @property
    def parent(self) -> IGroup:
        return self._parent

    @property
    def groups(self) -> Mapping[str, IGroup]:
        return DictView(self._groups)

    @property
    def rules(self) -> Mapping[str, IRule]:
        return DictView(self._rules)

    @property
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    def _get_info(self) -> GroupTreeInfo:
        return self._info


T_Child = TypeVar("T_Child", bound=IGroup)
_T_Self = TypeVar("_T_Self", bound="GroupOfGroups[Any]")


class GroupOfGroups(BasicMixin, SelectorMixin, MemoMixin, Generic[T_Child]):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: Dict[str, T_Child]
    _child_group_type: Union[None, Type[T_Child]] = None

    def __init__(
        self,
        child_group_type: Type[T_Child],
        dirname: Optional[StrOrPath] = None,
        prefix: Optional[StrOrPath] = None,
        *,
        loglevel: Optional[Loglevel] = None,
        use_default_logger: bool = True,
        logfile: Union[
            None,
            StrOrPath,
            Logger,
            WritableProtocol,
            Sequence[Union[StrOrPath, Logger, WritableProtocol]],
        ] = None,
    ):
        writer = basic_init_create_logwriter(
            loglevel, use_default_logger, logfile
        )

        memo_factory = StrHashMemo.create

        info = GroupTreeInfo(writer, memo_factory)

        self.__init_as_child__(info, self, ())

        self.set_prefix(parse_args_prefix(dirname, prefix))

        self.init(child_group_type)

    def __init_as_child__(
        self,
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._groups = {}

    def init(
        self: _T_Self,
        child_group_type: Type[T_Child],
        dirname: Optional[StrOrPath] = None,
        prefix: Optional[StrOrPath] = None,
    ) -> _T_Self:
        if self._child_group_type is not None:
            raise Exception(
                f"Child group type is already set ({self._child_group_type}). "
                "group_of_groups.init() may not be invoked if it was created "
                "as the root node using GroupOfGroups(...)"
            )

        tp = _get_type(child_group_type)

        if tp is None:
            raise TypeError(f"{tp} is not a valid type")

        if not issubclass(tp, IGroup):
            raise TypeError(f"child_group_type must be a subclass of IGroup")

        if inspect.isabstract(tp):
            raise TypeError(f"child_group_type must not be abstract")

        self._child_group_type = tp  # pyright: ignore

        if dirname is not None or prefix is not None:
            self.set_prefix(dirname, prefix=prefix)  # pyright: ignore

        return self

    def add_group(self, name: str) -> T_Child:
        if not isinstance(
            name, str
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        tp = self._child_group_type

        if tp is None:
            raise Exception(
                "Child group type must be set before adding children to "
                "a GroupOfGroups object. "
                "Please run `this_group.init(SomeChildGroupClass)` first."
            )

        g = tp.__new__(tp)
        g.__init_as_child__(self._info, self, (*self._name, name))

        self._groups[name] = g

        if name.isidentifier() and name[0] != "_" and not hasattr(self, name):
            setattr(self, name, g)

        return g

    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ""
        else:
            return self._name[-1]

    @property
    def namefq(self) -> str:
        return "/".join(self._name)

    @property
    def parent(self) -> IGroup:
        return self._parent

    @property
    def groups(self) -> Mapping[str, IGroup]:
        return DictView(self._groups)

    @property
    def rules(self) -> Mapping[str, IRule]:
        return DictView({})

    def __getitem__(self, k: str) -> T_Child:
        return self._groups[k]

    def __getattr__(self, k: str) -> T_Child:
        return self[k]

    @property
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    def _get_info(self) -> GroupTreeInfo:
        return self._info


class GroupOfRules(
    DynamicRuleContainerMixin,
    BasicMixin,
    BasicInitMixin,
    SelectorMixin,
    MemoMixin,
):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _rules: Dict[str, Rule[str]]

    def __init_as_child__(
        self, info: GroupTreeInfo, parent: IGroup, name: Tuple[str, ...]
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._rules = {}

    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        if name in self._rules:
            raise KeyError(f"Rule {name} already exists in the group")

        r = rule_factory()

        self._rules[name] = r

        if name.isidentifier() and not hasattr(self, name):
            setattr(self, name, r)

        return r

    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ""
        else:
            return self._name[-1]

    @property
    def namefq(self) -> str:
        return "/".join(self._name)

    @property
    def parent(self) -> IGroup:
        return self._parent

    @property
    def groups(self) -> Mapping[str, IGroup]:
        return DictView({})

    @property
    def rules(self) -> Mapping[str, IRule]:
        return DictView(self._rules)

    def __getitem__(self, k: str) -> Rule[str]:
        return self._rules[k]

    def __getattr__(self, k: str) -> Rule[str]:
        return self[k]

    @property
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    def _get_info(self) -> GroupTreeInfo:
        return self._info


class UntypedGroup(
    BasicMixin,
    DynamicRuleContainerMixin,
    BasicInitMixin,
    SelectorMixin,
    MemoMixin,
):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: Dict[str, IGroup]
    _rules: Dict[str, Rule[str]]

    def __init_as_child__(
        self, info: GroupTreeInfo, parent: IGroup, name: Tuple[str, ...]
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._groups = {}
        self._rules = {}

    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        if name in self._rules:
            raise KeyError(f"Rule {name} already exists in the group")

        r = rule_factory()

        self._rules[name] = r

        if name.isidentifier() and not hasattr(self, name):
            setattr(self, name, r)

        return r

    def add_group(
        self, name: str, child_group_class: Optional[Type[IGroup]] = None
    ) -> IGroup:
        if child_group_class is None:
            tp = UntypedGroup
        else:
            tp_ = _get_type(child_group_class)

            if tp_ is None:
                raise TypeError(f"{tp_} is not a valid type")

            if not issubclass(tp_, IGroup):
                raise TypeError(
                    f"child_group_type must be a subclass of IGroup"
                )

            if inspect.isabstract(tp_):
                raise TypeError(f"child_group_type must not be abstract")

            tp = tp_

        if not isinstance(
            name, str
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(
                f"A child group with the same {name} already exists. "
                "All child groups and rules must have unique names"
            )

        if name in self._rules:
            raise KeyError(
                f"A child rule with the same {name} already exists. "
                "All child groups and rules must have unique names"
            )

        g = tp.__new__(tp)
        g.__init_as_child__(self._info, self, (*self._name, name))

        self._groups[name] = g

        if name.isidentifier() and name[0] != "_" and not hasattr(self, name):
            setattr(self, name, g)

        return g

    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ""
        else:
            return self._name[-1]

    @property
    def namefq(self) -> str:
        return "/".join(self._name)

    @property
    def parent(self) -> IGroup:
        return self._parent

    @property
    def groups(self) -> Mapping[str, IGroup]:
        return DictView(self._groups)

    @property
    def rules(self) -> Mapping[str, IRule]:
        return DictView(self._rules)

    def _get_info(self) -> GroupTreeInfo:
        return self._info

    @property
    def name_tuple(self) -> Tuple[str, ...]:
        return self._name

    def __getitem__(self, k: str) -> Union[IGroup, IRule]:
        if k in self.groups:
            return self.groups[k]

        else:
            return self.rules[k]

    def __getattr__(self, __name: str) -> Any:
        if __name in self.groups:
            return self.groups[__name]
        elif __name in self.rules:
            return self.rules[__name]
        else:
            raise KeyError(f"No child group or rule named {__name}")


def _get_type(type_hint: Type[object]) -> Union[None, Type[Any]]:
    """
    Get instance of `type` from type hint.
    """
    if isinstance(type_hint, type):
        return type_hint

    origin = get_origin(type_hint)

    if isinstance(origin, type):
        return origin
    else:
        return None
