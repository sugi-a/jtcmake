from __future__ import annotations
import inspect
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
    get_origin,
    get_type_hints,
    Callable,
    overload,
)

from ..utils.strpath import StrOrPath
from ..utils.dict_view import DictView
from .core import IGroup, GroupTreeInfo, IRule
from .rule import Rule
from .group_mixins.basic import (
    BasicMixin,
    BasicInitMixin,
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


class GroupsGroup(
    BasicMixin, BasicInitMixin, SelectorMixin, MemoMixin, Generic[T_Child]
):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: Dict[str, T_Child]
    _child_group_type: Union[None, Type[T_Child]] = None

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

    def set_default_child(
        self, default_child_group_type: Type[T_Child]
    ) -> GroupsGroup[T_Child]:
        tp = _parse_child_group_type(default_child_group_type)
        self._child_group_type = tp  # pyright: ignore
        return self

    def set_props(
        self,
        default_child_group_type: Optional[Type[T_Child]],
        dirname: Optional[StrOrPath] = None,
        prefix: Optional[StrOrPath] = None,
    ) -> GroupsGroup[T_Child]:
        if default_child_group_type is not None:
            self.set_default_child(default_child_group_type)

        if dirname is not None or prefix is not None:
            self.set_prefix(dirname, prefix=prefix)  # pyright: ignore

        return self

    def add_group(
        self, name: str, child_group_type: Optional[Type[T_Child]] = None
    ) -> T_Child:
        if not isinstance(
            name, str
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        if child_group_type is None:
            if self._child_group_type is None:
                raise Exception(
                    "No child group type is available. "
                    "You must provide `child_group_type` or, in advance, "
                    "set the default child group type by "
                    "`GroupsGroup.set_default_child(some_group_type)` or "
                    "`GroupsGroup.set_props(some_group_type)`. "
                )

            tp: Type[T_Child] = self._child_group_type
        else:
            tp = _parse_child_group_type(child_group_type)  # pyright: ignore

        g = tp.__new__(tp)
        g.__init_as_child__(self._info, self, (*self._name, name))

        self._groups[name] = g

        if name.isidentifier() and name[0] != "_" and not hasattr(self, name):
            setattr(self, name, g)

        return g

    @property
    def parent(self) -> IGroup:
        return self._parent

    @property
    def groups(self) -> Mapping[str, T_Child]:
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


class RulesGroup(
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

    @overload
    def add_group(self, name: str, child_group_type: Type[T_Child]) -> T_Child:
        ...

    @overload
    def add_group(self, name: str) -> UntypedGroup:
        ...

    def add_group(self, name: object, child_group_type: Any = None) -> IGroup:
        if child_group_type is None:
            tp = UntypedGroup
        else:
            tp = _parse_child_group_type(child_group_type)

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

    def __getitem__(self, k: str) -> Any:
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


def _get_type(type_hint: object) -> Union[None, Type[Any]]:
    """
    Get instance of `type` from type hint (fully resolved one).
    On failure return None
    """
    if isinstance(type_hint, type):
        return type_hint

    origin = get_origin(type_hint)

    if isinstance(origin, type):
        return origin
    else:
        return None


def _parse_child_group_type(child_group_type: object) -> Type[IGroup]:
    tp = _get_type(child_group_type)

    if tp is None:
        raise TypeError(f"{tp} is not a valid type")

    if not issubclass(tp, IGroup):
        raise TypeError("Child group type must be a subclass of IGroup")

    if inspect.isabstract(tp):
        raise TypeError("Child group type must not be abstract")

    return tp
