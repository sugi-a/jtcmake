from __future__ import annotations
from logging import Logger
from typing import (
    Dict,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Generic,
    Union,
    List,
    Literal,
    Sequence,
    get_args,
    get_origin,
    get_type_hints,
    Callable,
)

from ..utils.strpath import StrOrPath
from ..utils.frozen_dict import DictView
from ..logwriter import Loglevel, WritableProtocol
from .core import IGroup, GroupTreeInfo, IRule, parse_args_prefix
from .rule import Rule
from .group_mixins.basic import (
    BasicMixin,
    BasicInitMixin,
    MemoKind,
    parse_args_create_memo_factory,
    basic_init_create_logwriter,
)
from .group_mixins.dynamic_container import DynamicRuleContainerMixin
from .group_mixins.memo import MemoMixin
from .group_mixins.selector import SelectorMixin


TMemoKind = Literal["str_hash", "pickle"]

V = TypeVar("V")

class StaticGroupBase(BasicMixin, BasicInitMixin, SelectorMixin, MemoMixin):
    _info: GroupTreeInfo
    _name: Tuple[str, ...]
    _groups: Dict[str, IGroup]
    _rules: Dict[str, Rule[str]]
    _parent: IGroup

    @classmethod
    def __create_as_child__(
        cls,
        type_hint: Type[IGroup],
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        del type_hint
        g = cls.__new__(cls)
        g.__init_as_child__(info, parent, name)
        return g

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

        for child_name, tp in get_type_hints(type(self)).items():
            fqcname = (*self._name, child_name)

            if tp == Rule:
                # Rule[str]
                r: Rule[str] = Rule.__new__(Rule)
                r.__init_partial__(fqcname, self._info, None, self)
                setattr(self, child_name, r)
                self._rules[child_name] = r
            elif hasattr(tp, "__origin__") and tp.__origin__ == Rule:
                # Rule[Literal[...]]
                keys = _parse_rule_generic_args(tp.__args__)
                r: Rule[str] = Rule.__new__(Rule)
                r.__init_partial__(fqcname, self._info, keys, self)
                setattr(self, child_name, r)
                self._rules[child_name] = r
            elif isinstance(tp, type) and issubclass(tp, IGroup) and tp != IGroup:
                # StaticGroup
                g = tp.__create_as_child__(tp, self._info, self, fqcname)
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

class GroupOfGroups(BasicMixin, SelectorMixin, MemoMixin, Generic[T_Child]):
    _name: Tuple[str, ...]
    _parent: IGroup
    _info: GroupTreeInfo
    _groups: Dict[str, T_Child]
    _child_type_hint: Type[T_Child]

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
        memo_kind: MemoKind = "str_hash",
        pickle_key: Union[None, str, bytes] = None,
    ):
        writer = basic_init_create_logwriter(
            loglevel, use_default_logger, logfile
        )

        memo_factory = parse_args_create_memo_factory(memo_kind, pickle_key)

        info = GroupTreeInfo(writer, memo_factory)

        self.__init_as_child__(child_group_type, info, self, ())

        self.set_prefix(parse_args_prefix(dirname, prefix))

    @classmethod
    def __create_as_child__(
        cls,
        type_hint: Type[IGroup],
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        g = cls.__new__(cls)

        origin = get_origin(type_hint)

        if origin is None or origin is not GroupOfGroups:
            raise TypeError(
                "Invalid type hint for GroupOfGroups. "
                "Type hint for GroupOfGroups must be like GroupOfGroups[...]. "
                f"Given {type_hint}"
            )

        type_args = get_args(type_hint)

        if len(type_args) != 1:
            raise TypeError(
                "Invalid type hint for GroupOfGroups. "
                "One type parameter must be given. "
                "e.g. GroupOfGroups[GroupOfRules]"
            )

        g.__init_as_child__(type_args[0], info, parent, name)

        return g

    def __init_as_child__(
        self,
        type_hint: Type[T_Child],
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        self._info = info
        self._parent = parent
        self._name = name
        self._groups = {}

        self._child_type_hint = _validate_child_group_type(
            type_hint
        )  # pyright: ignore

    def add(self, name: str) -> T_Child:
        if not isinstance(
            name, str
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        child_t = self._child_type_hint

        g = child_t.__create_as_child__(
            child_t, self._info, self, (*self._name, name)
        )

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

    @classmethod
    def __create_as_child__(
        cls,
        type_hint: Type[IGroup],
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        del type_hint
        g = cls.__new__(cls)
        g.__init_as_child__(info, parent, name)
        return g

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

    @classmethod
    def __create_as_child__(
        cls,
        type_hint: Type[IGroup],
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        del type_hint
        g = cls.__new__(cls)
        g.__init_as_child__(info, parent, name)
        return g

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
        # This is necessary for Pyright
        def _as_igroup(a: Type[IGroup]) -> Type[IGroup]:
            return a

        child_group_class_ = _as_igroup(child_group_class or UntypedGroup)

        if not issubclass(
            child_group_class_, IGroup
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("child_group_class must be subclass of IGroup")

        if not isinstance(
            name, str
        ):  # pyright: ignore [reportUnnecessaryIsInstance]
            raise TypeError("name must be str")

        if name in self._groups:
            raise KeyError(f"Child group {name} already exists")

        g = child_group_class_.__create_as_child__(
            child_group_class_, self._info, self, (*self._name, name)
        )

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


def _validate_child_group_type(tp: object) -> Type[IGroup]:
    dummy_g = UntypedGroup()
    dummy_info = dummy_g._get_info()  # pyright: ignore [reportPrivateUsage]

    if isinstance(tp, type):
        if issubclass(tp, IGroup):
            tp.__create_as_child__(tp, dummy_info, dummy_g, ("dummy",))
        else:
            raise TypeError("Type of child groups must be a subclass of IGroup")

        return tp

    origin: object = get_origin(tp)

    if not isinstance(origin, type) or not issubclass(origin, IGroup):
        raise TypeError("Invalid type hint {tp}.")
    else:
        origin.__create_as_child__(
            tp, dummy_info, dummy_g, ("dummy",)  # pyright: ignore
        )

    return tp  # pyright: ignore
