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
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def add(
        self, name: StrOrPath, method: Callable[P, object], /
    ) -> Callable[P, Rule[str]]:
        ...

    def add(
        self, name: object, outs: object, method: object = None
    ) -> Callable[..., Rule[str]]:
        """
        Create a temporary function for adding a rule to the group.

        Args:
            name: name of the rule.
            output_files: if not specified, ``name`` will be used for
                ``output_files``.
                The following three forms are accepted.

                * **dict-style** (``{"foo": foo_file, "bar": bar_file, ...}``):

                  ``foo``, ``bar``, ... are the *file keys* and ``foo_file``,
                  ``bar_file``, ... are the file paths.
                  File keys must be str. File paths may be either str or
                  PathLike including ``jtcmake.File`` and ``jtcmake.VFile``.
                  If a given file path is neither ``File`` or ``VFile``, it
                  will be converted to ``File`` by ``jtcmake.File(file_path)``.
                * **list-style** (``[foo_file, bar_file, ...]``):

                  It is equivalent to
                  ``{str(foo_file): foo_file, str(bar_file): bar_file}``
                * **Atom-style** (``foo_file``):

                  It is equivalent to ``{str(foo_file): foo_file}``
            method: function to create the output files

        Returns:
            *rule_adder*, a temporary function whose signature is the same as
            the argument ``method``.
            When called as ``rule_adder(*args, **kwargs)``, it appends
            a new rule to the group.

            On making the rule, ``method`` is called as
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

        return self._add(name, outs, method, IFile_fact=File)

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
    ) -> Callable[P, Rule[str]]:
        ...

    @overload
    def addvf(
        self, name: StrOrPath, method: Callable[P, object], /
    ) -> Callable[P, Rule[str]]:
        ...

    def addvf(
        self, name: object, outs: object, method: object = None
    ) -> Callable[..., Rule[str]]:
        """
        Create a temporary function for adding a rule to the group.

        This method is equal to ``self.add`` except the default file
        constructor is ``jtcmake.VFile`` instead of ``File``.

        See the doc of ``self.add`` for more information.

        """
        return self._add(name, outs, method, IFile_fact=VFile)

    def _add(
        self,
        name: object,
        outs: object,
        method: object = None,
        *,
        IFile_fact: Callable[[StrOrPath], IFile],
    ) -> Callable[..., Rule[str]]:
        if method is None:
            outs, method = name, outs

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        outs_: Dict[str, IFile] = parse_args_output_files(
            name_, None, outs, IFile_fact
        )

        def _add(*args: object, **kwargs: object) -> Rule[str]:
            return self._add_rule(name_, outs_, method, args, kwargs)

        return _add

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
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        return self._add_deco(name, output_files, IFile_fact=File)

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
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        return self._add_deco(name, output_files, IFile_fact=VFile)

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
        ] = None,
        *,
        IFile_fact: Callable[[StrOrPath], IFile],
    ) -> Callable[[_T_deco_f], _T_deco_f]:
        if output_files is None:
            output_files = name

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        output_files_: Dict[str, IFile] = parse_args_output_files(
            name_, None, output_files, IFile_fact
        )

        def decorator(method: _T_deco_f):
            args, kwargs = Rule_init_parse_deco_func(method)
            self._add_rule(name_, output_files_, method, args, kwargs)
            return method

        return decorator

    def _add_rule(
        self,
        name: str,
        yfiles: Mapping[str, IFile],
        method: object,
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
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
            )

            return r

        return self._add_rule_lazy(name, _factory)

    @abstractmethod
    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        ...
