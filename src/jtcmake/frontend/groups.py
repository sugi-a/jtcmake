from __future__ import annotations
from os import PathLike
from typing import (
    Mapping, Tuple, Type, TypeVar, Generic, Union, List,
    Literal, Sequence, get_type_hints, Callable
)

from .group_mixins.child_adder import DynamicRuleContainer


from .group_common import IGroup, GroupTreeInfo, IRule, ItemMap, priv_add_to_itemmap
from .rule import Rule
from .group_base import GroupBase

StrOrPath = Union[str, PathLike[str]]

TMemoKind = Literal["str_hash", "pickle"]

V = TypeVar("V")

class StaticGroupBase(GroupBase):
    _info: GroupTreeInfo
    _name: Sequence[str]
    _groups: ItemMap[IGroup]
    _rules: ItemMap[Rule[str]]
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

        self._groups = ItemMap()
        self._rules = ItemMap()

        for child_name, tp in get_type_hints(type(self).__annotations__).items():
            fqcname = (*self._name, child_name)

            if tp == Rule:
                # Rule[str]
                r: Rule[str] = Rule.__new__(Rule)
                r.__init_partial__(fqcname, self._info, None, self)
                setattr(self, child_name, r)
                priv_add_to_itemmap(self._rules, child_name, r)
            elif hasattr(tp, "__origin__") and tp.__origin__ == Rule:
                # Rule[Literal[...]]
                keys = _parse_rule_generic_args(tp.__args__)
                r: Rule[str] = Rule.__new__(Rule)
                r.__init_partial__(fqcname, self._info, keys, self)
                setattr(self, child_name, r)
                priv_add_to_itemmap(self._rules, child_name, r)
            elif issubclass(tp, IGroup):
                # StaticGroup
                g = tp.__new__(tp)
                g.__init_as_child__(self._info, self, (*self._name, child_name))

                setattr(self, child_name, g)
                priv_add_to_itemmap(self._groups, child_name, g)


    @property
    def initialized_whole_tree(self) -> bool:
        return len(self._info.rules_to_be_init) == 0


    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ''
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
        return self._groups

    @property
    def rules(self) -> Mapping[str, IRule]:
        return self._rules


T_Child = TypeVar("T_Child", bound=IGroup)

class GroupOfGroups(GroupBase, Generic[T_Child]):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: ItemMap[T_Child]

    def __init_as_child__(
        self, info: GroupTreeInfo, parent: IGroup, name: Tuple[str, ...],
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._groups = ItemMap()


    def add(self, name: str, child_group_class: Type[T_Child]) -> T_Child:
        if not issubclass(child_group_class, IGroup):
            raise TypeError("child_group_class must be subclass of IGroup")

        if not isinstance(name, str):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        g = child_group_class.__new__(child_group_class)
        g.__init_as_child__(self._info, self, (*self._name, name))

        priv_add_to_itemmap(self._groups, name, g)

        if name.isidentifier() and name[0] != "_" and not hasattr(self, name):
            setattr(self, name, g)

        return g
        

    @property
    def initialized_whole_tree(self) -> bool:
        return len(self._info.rules_to_be_init) == 0


    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ''
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
        return self._groups

    @property
    def rules(self) -> Mapping[str, IRule]:
        return {}

    def __getitem__(self, k: str) -> IGroup:
        return self._groups[k]

    def __getattr__(self, k: str) -> IGroup:
        return self[k]


class GroupOfRules(DynamicRuleContainer, GroupBase):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _rules: ItemMap[Rule[str]]

    def __init_as_child__(
        self, info: GroupTreeInfo, parent: IGroup, name: Tuple[str, ...]
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._rules = ItemMap()


    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        if name in self._rules:
            raise KeyError(f"Rule {name} already exists in the group")

        r = rule_factory()

        priv_add_to_itemmap(self._rules, name, r)

        if name.isidentifier() and not hasattr(self, name):
            setattr(self, name, r)

        return r


    @property
    def initialized_whole_tree(self) -> bool:
        return len(self._info.rules_to_be_init) == 0


    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ''
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
        return {}

    @property
    def rules(self) -> Mapping[str, IRule]:
        return self._rules

    def __getitem__(self, k: str) -> Rule[str]:
        return self._rules[k]

    def __getattr__(self, k: str) -> Rule[str]:
        return self[k]


class UntypedGroup(GroupBase, DynamicRuleContainer):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: ItemMap[IGroup]
    _rules: ItemMap[Rule[str]]

    def __init_as_child__(
        self, info: GroupTreeInfo, parent: IGroup, name: Tuple[str, ...]
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._groups = ItemMap()
        self._rules = ItemMap()


    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        if name in self._rules:
            raise KeyError(f"Rule {name} already exists in the group")

        r = rule_factory()

        priv_add_to_itemmap(self._rules, name, r)

        if name.isidentifier() and not hasattr(self, name):
            setattr(self, name, r)

        return r

    def add_group(self, name: str, child_group_class: Type[T_Child]) -> IGroup:
        if not issubclass(child_group_class, IGroup):
            raise TypeError("child_group_class must be subclass of IGroup")

        if not isinstance(name, str):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        g = child_group_class.__new__(child_group_class)
        g.__init_as_child__(self._info, self, (*self._name, name))

        priv_add_to_itemmap(self._groups, name, g)

        if name.isidentifier() and name[0] != "_" and not hasattr(self, name):
            setattr(self, name, g)
        
        return g


    @property
    def initialized_whole_tree(self) -> bool:
        return len(self._info.rules_to_be_init) == 0


    @property
    def name(self) -> str:
        if len(self._name) == 0:
            return ''
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
        return self._groups

    @property
    def rules(self) -> Mapping[str, IRule]:
        return {}



def _parse_rule_generic_args(
    args: Tuple[object, ...]
) -> Union[None, List[str]]:
    if len(args) != 1:
        raise TypeError(
            f"Arguments for a generic Rule must be str or LiteralString. "
            f"Given {args}"
        )

    arg = args[0]

    if isinstance(arg, type) and issubclass(arg, str):
        return None


    origin_t = getattr(arg, "__origin__", None)

    if origin_t != Literal:
        raise TypeError(f"Expected LiteralString. Given {arg}")

    keys = getattr(arg, "__args__", None)

    if not isinstance(keys, Sequence):
        raise TypeError(f"Invalid type hint {arg}")

    return [
        _assert_isstr(k)
        for k in keys  # pyright: ignore [reportUnknownVariableType]
    ]


def _assert_isstr(o: object) -> str:
    if isinstance(o, str):
        return o
    else:
        raise TypeError("Expected str, given {o}")


