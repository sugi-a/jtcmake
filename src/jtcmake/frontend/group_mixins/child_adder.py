from os import PathLike
from abc import ABCMeta, abstractmethod
from typing import Dict, Sequence, TypeVar, Union, Tuple, Any, overload, Mapping, Callable

from typing_extensions import ParamSpec

from ...rule.file import IFile, File
from ..group_common import IGroup
from ..rule import normalize_output_files, Rule_init_parse_deco_func, Rule

StrOrPath = Union[str, PathLike[str]]

P = ParamSpec("P")
K = TypeVar("K", bound=str)

class DynamicRuleContainer(IGroup, metaclass=ABCMeta):
    @overload
    def add(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[str]]],
            K,
            PathLike[str]
        ],
        method: Callable[P, object],
        /
    ) -> Callable[P, None]:
        ...

    @overload
    def add(
        self,
        name: StrOrPath,
        output_files: Union[
            Mapping[K, StrOrPath],
            Sequence[Union[K, PathLike[Any]]], K, PathLike[Any]
        ],
        /
    ) -> Callable[[Callable[[], object]], None]:
        ...

    @overload
    def add(
        self,
        name: StrOrPath,
        method: Callable[P, object],
        /
    ) -> Callable[P, None]:
        ...

    @overload
    def add(
        self,
        name: StrOrPath,
        /
    ) -> Callable[[Callable[[], object]], None]:
        ...

    def add(self, name: object, *args: object) -> Callable[..., Any]:
        name_, outs, method = _parse_args(name, args, File)

        if method is None:
            def _deco(method: object):
                args, kwargs = Rule_init_parse_deco_func(method)
                self._add_rule(name_, outs, method, args, kwargs)

            return _deco
        else:
            def _add(*args: object, **kwargs: object):
                self._add_rule(name_, outs, method, args, kwargs)

            return _add


    def _add_rule(
        self,
        name: str,
        yfiles: Mapping[str, IFile],
        method: object,
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
    ) -> Rule[str]:
        if name in self.rules:
            raise KeyError(f"Rule {name} already exists in the group")

        def _factory() -> Rule[str]:
            r: Rule[str] = Rule.__new__(Rule)

            r.__init_at_once__(
                (*self.name_tuple, name),
                self._get_info(),
                self,
                yfiles, method, args, kwargs
            )

            return r

        return self._add_rule_lazy(name, _factory)


    @abstractmethod
    def _add_rule_lazy(
        self, name: str, rule_factory: Callable[[], Rule[str]]
    ) -> Rule[str]:
        ...


def _parse_args(
    name: object,
    args: Tuple[object, ...],
    IFile_factory: Callable[[StrOrPath], IFile]
) -> Tuple[str, Dict[str, IFile], Union[None, Callable[..., object]]]:
    if not isinstance(name, (str, PathLike)):
        raise TypeError(f"name must be str or PathLike")

    if len(args) == 0:
        return (
            str(name),
            normalize_output_files(None, name, IFile_factory),
            None,
        )

    if len(args) == 1:
        if callable(args[0]):
            return (
                str(name),
                normalize_output_files(None, name, IFile_factory),
                args[0],
            )
        else:
            return (
                str(name),
                normalize_output_files(None, args[0], IFile_factory),
                None,
            )

    if len(args) == 2:
        if not callable(args[1]):
            raise TypeError(f"method must be callable. Given {args[1]}")

        return (
            str(name),
            normalize_output_files(None, args[0], IFile_factory),
            args[1],
        )

    raise TypeError(f"Too many arguments.")
