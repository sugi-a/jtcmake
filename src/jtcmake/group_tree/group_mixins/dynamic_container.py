from __future__ import annotations
from os import PathLike
from abc import ABCMeta, abstractmethod
from typing import (
    Dict,
    Optional,
    Sequence,
    TypeVar,
    Union,
    Tuple,
    overload,
    Mapping,
    Callable,
)

from typing_extensions import ParamSpec

from ..file import File, VFile
from ..core import IGroup, IFile
from ..rule import parse_args_output_files, Rule_init_parse_deco_func, Rule
from ...utils.strpath import StrOrPath

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

    def add(
        self,
        name: object,
        outs: object,
        method: object = None,
        noskip: bool = False,
    ) -> Callable[..., Rule[str]]:
        """
        Create a temporary function to add a rule to this group.

        This method works similarly to :func:`Rule.init`.
        See its documentation for details.

        Args:
            name: name of the rule.
            output_files: if not specified, ``name`` will be used.
            method: function to create the output files


        Returns:
            *rule_adder*, a temporary function whose signature is the same as
            the given ``method``.
            Calling it as ``rule_adder(*args, **kwargs)`` appends
            a new rule to the group.

            While executing this rule, ``method`` is called as
            ``method(*args, **kwargs)``.

        Example:

            ::

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

    def addvf(
        self,
        name: object,
        outs: object,
        method: object = None,
        noskip: bool = False,
    ) -> Callable[..., Rule[str]]:
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
    ) -> Callable[..., Rule[str]]:
        if method is None:
            outs, method = name, outs

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        outs_: Dict[str, IFile] = parse_args_output_files(
            name_, None, outs, IFile_fact
        )

        def _rule_adder(*args: object, **kwargs: object) -> Rule[str]:
            return self._add_rule(name_, outs_, method, args, kwargs, noskip)

        return _rule_adder

    def add_deco(
        self,
        name: StrOrPath,
        output_files: Optional[
            Union[
                Mapping[K, StrOrPath],
                Sequence[Union[str, PathLike[str]]],
                str,
                PathLike[str],
            ]
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        """
        Create a temporary decorator function to add a rule to this group.
        This is a decorator version of :func:`add`.
        It's useful when you want to define a method for the new rule
        on-the-fly instead of passing an existing function
        (see the examples below).

        This method workds similarly to :func:`Rule.init_deco`.
        See its documentation for detail.

        Args:
            name: name of the rule to be added
            output_files: output files of the rule.
                See :func:`add` for more information.
                Just like :func:`add`, file paths will be internally
                converted to :class:`jtcmake.File` if they aren't either
                :class:`jtcmake.File` or :class:`jtcmake.VFile`.

        Returns:
            **rule_method_decorator**.

        Usage:
            Invoking the ``rule_method_decorator`` with the method you want to
            bind to the new rule creates the rule and append it to this group.

            All the arguments to the method must have a default value. ::

                g.add_deco("myrule1")(lambda p=SELF: p.write_text("abc"))

                @g.add_deco("myrule2", "out.txt")
                def method_for_myrule2(src=g.myrule1[0], dst=SELF, n=2):
                    text = src.read_text()
                    dst.write_text(text * 2)

                g.make()

                assert g.myrule2[0].read_text() == "abcabc"

            The above is equivalent to ::

                g.add("myrule1", lambda p=SELF: p.write_text("abc"))(SELF)

                def method_for_myrule2(src=g.myrule1[0], dst=SELF, n=2):
                    text = src.read_text()
                    dst.write_text(text * 2)

                g.add("myrule2", "out.txt", method_for_myrule2)(
                    g.myrule1[0], SELF, 2
                )
        """
        return self._add_deco(name, output_files, File, noskip)

    def addvf_deco(
        self,
        name: StrOrPath,
        output_files: Optional[
            Union[
                Mapping[K, StrOrPath],
                Sequence[Union[str, PathLike[str]]],
                str,
                PathLike[str],
            ]
        ] = None,
        /,
        *,
        noskip: bool = False,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        """
        Create a temporary decorator function to add a rule to this group.

        This method is equal to :func:`add_deco` except the default file
        constructor is :class:`jtcmake.VFile` instead of :class:`File`.

        See :func:`add_deco` and :func:`add` for more information.
        """
        return self._add_deco(name, output_files, VFile, noskip)

    def _add_deco(
        self,
        name: StrOrPath,
        output_files: Optional[
            Union[
                Mapping[K, StrOrPath],
                Sequence[Union[str, PathLike[str]]],
                str,
                PathLike[str],
            ]
        ],
        IFile_fact: Callable[[StrOrPath], IFile],
        noskip: bool,
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        if output_files is None:
            output_files = name

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        output_files_: Dict[str, IFile] = parse_args_output_files(
            name_, None, output_files, IFile_fact
        )

        def rule_method_decorator(method: _T_deco_f):
            args, kwargs = Rule_init_parse_deco_func(method)
            self._add_rule(name_, output_files_, method, args, kwargs, noskip)
            return method

        return rule_method_decorator

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
