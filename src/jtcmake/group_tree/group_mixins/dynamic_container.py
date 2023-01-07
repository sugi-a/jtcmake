from __future__ import annotations

from abc import ABCMeta, abstractmethod
from os import PathLike
from typing import (
    Callable,
    Dict,
    Mapping,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from typing_extensions import ParamSpec

from ...utils.strpath import StrOrPath
from ..core import IFile, IGroup
from ..file import File, VFile
from ..rule import Rule, Rule_init_parse_deco_func, parse_args_output_files

P = ParamSpec("P")
K = TypeVar("K", bound=str)
_T_deco_f = TypeVar("_T_deco_f", bound=Callable[[], object])


class DynamicRuleContainerMixin(IGroup, metaclass=ABCMeta):
    @overload
    def add(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[str]]],
            K,
            PathLike[str],
        ],
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def add(
        self,
        name: StrOrPath,
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def add(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[str]]],
            K,
            PathLike[str],
            None,
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        ...

    def add(
        self,
        name: object,
        outs: object = None,
        method: object = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[..., object]:
        """
        Create a temporary function to add a rule to this group.

        This method works similarly to :func:`Rule.init`.
        See its documentation for details.

        Args:
            name: name of the rule.
            output_files: if not specified, ``name`` will be used.
            method: function to create the output files


        Returns:
            If ``method`` is provided, it returns a function *rule_adder*,
            whose signature is the same as the given ``method``.
            Calling it as ``rule_adder(*args, **kwargs)`` appends
            a new rule to the group.

            If ``method`` is not provided, it returns a decorator function
            *method_decorator*, which consumes a function and appends a new rule
            whose method is the given function.

            While executing this rule, ``method`` is called as
            ``method(*args, **kwargs)``.

        Example:

            With ``method`` provided::

                from __future__ import annotations
                from pathlib import Path
                from jtcmake import RulesGroup, SELF, VFile, File

                g = RulesGroup("out")

                def split_write(text: str, file1: Path, file2: Path):
                    # Write first half of ``text`` to file1 and the rest to file2
                    n = len(text)
                    file1.write_text(text[: n // 2])
                    file2.write_text(text[n // 2: n])

                def cat(srcs: list[Path], dst: Path):
                    with dst.open("w") as f:
                        f.writelines(src.read_text() for src in srcs)

                # File path may be str or PathLike
                g.add("foo", {"a": "a.txt", "b": Path("b.txt")}, split_write)("abcd", SELF[0], SELF[1])

                g.add("bar", ["x.txt", VFile("y.txt")], split_write)("efgh", SELF[0], SELF[1])

                g.add("baz", "baz.txt", cat)([g.foo[0], g.foo[1], g.bar[0], g.bar[1]], SELF)

                # file paths of str or PathLike (excluding File/VFile) are
                # internally converted to File
                assert isinstance(g.bar["x.txt"], File)

                # file paths of VFile remains VFile
                assert isinstance(g.bar["y.txt"], VFile)

                g.make()

                assert Path("out/a.txt").read_text() == "ab"
                assert Path("out/b.txt").read_text() == "cd"
                assert Path("out/x.txt").read_text() == "ef"
                assert Path("out/y.txt").read_text() == "gh"
                assert Path("out/baz.txt").read_text() == "abcdefgh"

            Without ``method``::

                from __future__ import annotations
                from pathlib import Path
                from jtcmake import RulesGroup, SELF, VFile, File

                g = RulesGroup("out")

                @g.add("foo")
                def foo(dst: Path = SELF):
                    dst.write_text("abc")

                @g.add("bar")
                def bar(dst: Path = SELF):
                    dst.write_text("xyz")

                @g.add("baz")
                def baz(dst: Path = SELF, srcs: list[Path] = [g.foo, g.bar]):
                    with dst.open("w") as f:
                        f.writelines(src.read_text() for src in srcs)

                g.make()

                assert Path("out/foo").read_text() == "abc"
                assert Path("out/bar").read_text() == "xyz"
                assert Path("out/baz").read_text() == "abcxyz"
        """

        return self._add(name, outs, method, File, noskip)

    @overload
    def addvf(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[str]]],
            K,
            PathLike[str],
        ],
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def addvf(
        self,
        name: StrOrPath,
        method: Callable[P, object],
        /,
        *,
        noskip: bool = False,
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def addvf(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[str]]],
            K,
            PathLike[str],
            None,
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        ...

    def addvf(
        self,
        name: object,
        outs: object = None,
        method: object = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[..., object]:
        """
        Create a temporary function to add a rule to this group.

        This method is equal to :func:`self.add <.add>` except the default
        file class is :class:`VFile` instead of :class:`File`.

        See the documentation of :func:`self.add <.add>` for more information.
        """
        return self._add(name, outs, method, VFile, noskip)

    def _add(
        self,
        name: object,
        outs: object,
        method: object,
        IFile_fact: Callable[[StrOrPath], IFile],
        noskip: bool,
    ) -> Callable[..., object]:
        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        if method is None:
            if callable(outs):
                outs, method = name, outs
            elif outs is None:
                outs = name

        assert callable(method) or method is None

        outs_: Dict[str, IFile] = parse_args_output_files(
            name, None, outs, IFile_fact
        )

        if method is None:

            def method_decorator(method: Callable[[], object]):
                args, kwargs = Rule_init_parse_deco_func(method)
                self._add_rule(name, outs_, method, args, kwargs, noskip)
                return method

            return method_decorator
        else:

            def rule_adder(*args: object, **kwargs: object) -> Rule[str]:
                return self._add_rule(name, outs_, method, args, kwargs, noskip)

            return rule_adder

    def _add_rule(
        self,
        name: str,
        yfiles: Mapping[str, IFile],
        method: object,
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
        noskip: bool,
    ) -> Rule[str]:
        if name in self.rules:
            raise KeyError(
                f"A child rule with the same {name} already exists. "
                "All child groups and rules must have unique names"
            )

        if name in self.groups:
            raise KeyError(
                f"A child group with the same {name} already exists. "
                "All child groups and rules must have unique names"
            )

        def _factory() -> Rule[str]:
            r: Rule[str] = Rule.__new__(Rule)

            r.__init_at_once__(
                (*self.name_tuple, name),
                self._get_info(),
                self,
                yfiles,
                method,
                args,
                kwargs,
                noskip,
            )

            return r

        return self._add_rule_lazy(name, _factory)

    @abstractmethod
    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        ...
