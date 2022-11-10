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
    Any,
    overload,
    Mapping,
    Callable,
)

from typing_extensions import ParamSpec

from ..file import IFile, File
from ..core import IGroup
from ..rule import parse_args_output_files, Rule_init_parse_deco_func, Rule
from ...utils.strpath import StrOrPath

P = ParamSpec("P")
K = TypeVar("K", bound=str)


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
    ) -> Callable[P, None]:
        ...

    @overload
    def add(
        self, name: StrOrPath, method: Callable[P, object], /
    ) -> Callable[P, None]:
        ...

    def add(
        self, name: object, outs: object, method: object = None
    ) -> Callable[..., Any]:
        if method is None:
            outs, method = name, outs

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        outs_: Dict[str, IFile] = parse_args_output_files(
            name_, None, outs, File
        )

        def _add(*args: object, **kwargs: object):
            self._add_rule(name_, outs_, method, args, kwargs)

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
    ) -> Callable[[Callable[[], object]], None]:
        if output_files is None:
            output_files = name

        if not isinstance(name, str):
            raise TypeError("name must be str or os.PathLike")

        name_ = str(name)

        output_files_: Dict[str, IFile] = parse_args_output_files(
            name_, None, output_files, File
        )

        def decorator(method: object):
            args, kwargs = Rule_init_parse_deco_func(method)
            self._add_rule(name_, output_files_, method, args, kwargs)

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
