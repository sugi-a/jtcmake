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
from .core import IGroup, GroupTreeInfo
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
    """
    Base class for static groups.

    A static group should be defined by subclassing StaticGroupBase.
    It must have type annotations to represent its child groups and rules.  ::

        class CustomStaticGroup(StaticGroupBase):
            child_rule1: Rule[str]
            child_rule2: Rule[Literal["a"]]
            child_group1: AnotherStaticGroup
            child_group2: RulesGroup

            '''
            Generic type parameters like ``[str]`` in this example is ignored
            at runtime. They are just hints for the type checker and IDE.
            '''

    The child nodes are automatically instanciated when the parent is
    instanciated. So you can read them without assigning values::

        g = CustomStaticGroup()
        print(g.child_rule1)
        print(g.child_group1)

    Remember that the child rules are automatically instanciated but not
    *initialized* . you have to manually initialize them with
    ``Rule.init`` ::

        g.child_rule1.init("child_file1.txt", copy)(souce_file, SELF)

    As a design pattern, it is recommended to have an initializer method
    that initializes the child rules and calls the initializer of the child
    groups to recursively initialize all the rules in the sub-tree.

    .. testcode::

        from __future__ import annotations
        from pathlib import Path
        from jtcmake import StaticGroupBase, Rule, SELF


        class MyGroup(StaticGroupBase):
            __globals__ = globals()  # For Sphinx's doctest. Not necessary in normal situations.
            child_rule: Rule[str]
            child_group: MyChildGroup

            def init(self, text: str, repeat: int) -> MyGroup:
                # Initializer for this class. The method name "init" is not
                # reserved so you can choose your own one.

                # Initialize the direct child rules
                self.child_rule.init("<R>.txt", Path.write_text)(SELF, text)

                # Initialize the child group
                self.child_group.init(self.child_rule, repeat)

                return self


        class MyChildGroup(StaticGroupBase):
            __globals__ = globals()  # For Sphinx's doctest. Not necessary in normal situations.
            foo: Rule[str]

            def init(self, src: Path, repeat: int) -> MyChildGroup:
                @self.foo.init("<R>.txt")
                def _(src=src, dst=SELF, repeat=repeat):
                    text = src.read_text()
                    dst.write_text(text * repeat)

                return self


        g = MyGroup("out").init("abc", 2)
        g.make()

        assert Path("out/child_rule.txt").read_text() == "abc"
        assert Path("out/child_group/foo.txt").read_text() == "abcabc"

        import shutil; shutil.rmtree("out")  # Cleanup for Sphinx's doctest

    .. note::
       When you override the ``__init__`` method, you have to call
       ``super().__init__`` in it with appropriate arguments.

    """

    __globals__: Optional[Dict[str, object]] = None
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

        try:
            if self.__globals__ is None:
                hints = get_type_hints(type(self))
            else:
                hints = get_type_hints(type(self), None, self.__globals__)
        except Exception as e:
            raise Exception(
                f"Failed to get type hints of static group class {type(self)}."
            ) from e

        for child_name, type_hint in hints.items():
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
    def rules(self) -> Mapping[str, Rule[str]]:
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
    """
    A group that contains groups as children.

    When writing type hints, children's type can be passed as a generic
    type parameter like ``GroupsGroup[SomeGroupClass]`` .

    .. testcode::

        from pathlib import Path
        from typing import Union
        from jtcmake import SELF, StaticGroupBase, GroupsGroup, Rule

        class Child1(StaticGroupBase):
            __globals__ = globals()  # For Sphinx's doctest. Not necessary in normal situations.
            rule1: Rule[str]

            def init(self, text: str):
                self.rule1.init("<R>.txt", Path.write_text)(SELF, text)
                return self

        class Child2(StaticGroupBase):
            __globals__ = globals()  # For Sphinx's doctest. Not necessary in normal situations.
            rule2: Rule[str]

            def init(self, text: str):
                self.rule2.init("<R>.txt", Path.write_text)(SELF, text * 2)

        g: GroupsGroup[Union[Child1, Child2]] = GroupsGroup("out")

        # Set the child class to use by default
        g.set_default_child(Child1)

        for i in range(2):
            # Child1 will be the child class
            g.add_group(f"child1-{i}").init(str(i))

        for i in range(2):
            # Explicity giving the child class Child2
            g.add_group(f"child2-{i}", Child2).init(str(i))

        g.make()

        assert Path("out/child1-0/rule1.txt").read_text() == "0"
        assert Path("out/child1-1/rule1.txt").read_text() == "1"
        assert Path("out/child2-0/rule2.txt").read_text() == "00"
        assert Path("out/child2-1/rule2.txt").read_text() == "11"

        import shutil; shutil.rmtree("out")  # Cleanup for Sphinx's doctest
    """

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
        """
        Sets the default child class, which will be used when
        :func:`GroupsGroup.add_group` is called with ``child_group_type``
        unspecified.
        """
        tp = _parse_child_group_type(default_child_group_type)
        self._child_group_type = tp  # pyright: ignore
        return self

    def set_props(
        self,
        default_child_group_type: Optional[Type[T_Child]] = None,
        dirname: Optional[StrOrPath] = None,
        prefix: Optional[StrOrPath] = None,
    ) -> GroupsGroup[T_Child]:
        """
        Convenient method that works as :func:`set_default_child`
        and `set_prefix` combined.
        """
        if default_child_group_type is not None:
            self.set_default_child(default_child_group_type)

        if dirname is not None or prefix is not None:
            self.set_prefix(dirname, prefix=prefix)  # pyright: ignore

        return self

    def add_group(
        self, name: str, child_group_type: Optional[Type[T_Child]] = None
    ) -> T_Child:
        """
        Append a child group to this group.

        Args:
            name (str): name of the new child group.
            child_group_type:
                class of the new child group. If not specified, and if the
                default child group class is available (set by
                ``self.set_default_child``), it will be used. Otherwise,
                an exception will be raised.
        """
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
    def rules(self) -> Mapping[str, Rule[str]]:
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
    """
    A group that contains rules as children.

    .. testcode::

        from pathlib import Path
        from jtcmake import RulesGroup, SELF

        g = RulesGroup("out")

        for i in range(3):
            g.add(f"child{i}.txt", Path.write_text)(SELF, str(i))

        g.make()

        assert Path("out/child0.txt").read_text() == "0"
        assert Path("out/child1.txt").read_text() == "1"
        assert Path("out/child2.txt").read_text() == "2"

        import shutil; shutil.rmtree("out")  # Cleanup for Sphinx's doctest
    """

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
    def rules(self) -> Mapping[str, Rule[str]]:
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
    """
    A group that have groups and rules as children.

    .. note::
        Type annotation for this class is weak and you won't get much support
        from static type checkers and IDEs.
        It is recommended to use :class:`StaticGroupBase`, :class:`GroupsGroup`, and
        :class:`RulesGroup` when writing a long code.

    .. testcode::

        from pathlib import Path
        from jtcmake import UntypedGroup, SELF, Rule, StaticGroupBase

        def add1(src: Path, dst: Path):
            dst.write_text(str(int(src.read_text()) + 1))

        g = UntypedGroup("out")

        @g.add("rule0")
        def _write_0(p: Path = SELF):
            p.write_text("0")

        g.add("rule1", add1)(g.rule0, SELF)

        # ``add_group`` with ``child_group_type=None`` adds an UntypedGroup
        g.add_group("group1")

        g.group1.add("rule2", add1)(g.rule1, SELF)

        class Child(StaticGroupBase):
            __globals__ = globals()  # For Sphinx's doctest. Not necessary in normal situations.
            rule: Rule

        g.add_group("group2", Child)

        g.group2.rule.init("rule3", add1)(g.group1.rule2, SELF)

        g.make()

        assert Path("out/rule0").read_text() == "0"
        assert Path("out/rule1").read_text() == "1"
        assert Path("out/group1/rule2").read_text() == "2"
        assert Path("out/group2/rule3").read_text() == "3"

        import shutil; shutil.rmtree("out")  # Cleanup for Sphinx's doctest
    """

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
        """
        Append a child group to this group.

        Args:
            name (str): name of the new child group.
            child_group_type: class of the new child group.
                If not specified, ``UntypedGroup`` will be used.
        """
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
    def rules(self) -> Mapping[str, Rule[str]]:
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
