from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any, List, Tuple

from ..utils.nest import map_structure


class IMemoAtom(metaclass=ABCMeta):
    @property
    @abstractmethod
    def memo_value(self) -> object:
        """
        Returns:
            object to be memoized
        """
        ...


class ILazyMemoValue(metaclass=ABCMeta):
    @abstractmethod
    def __call__(self) -> object:
        ...


class _EvalLazyMemoValues:
    __slots__ = ("lazy_memo_values",)

    def __init__(self, lazy_memo_values: List[ILazyMemoValue]):
        self.lazy_memo_values = lazy_memo_values

    def __call__(self) -> List[object]:
        return [v() for v in self.lazy_memo_values]


def unwrap_memo_values(nest: object) -> Tuple[object, _EvalLazyMemoValues]:
    lazy_values: List[ILazyMemoValue] = []

    def _unwrap_atom(atom: object):
        if isinstance(atom, IMemoAtom):
            v = atom.memo_value
            if isinstance(v, ILazyMemoValue):
                lazy_values.append(v)
                return None
            else:
                return v
        else:
            return atom

    nest = map_structure(_unwrap_atom, nest)

    return nest, _EvalLazyMemoValues(lazy_values)


class IAtom(IMemoAtom, metaclass=ABCMeta):
    @property
    @abstractmethod
    def real_value(self) -> object:
        ...


def unwrap_real_values(args: object) -> object:
    def repl(v: object) -> object:
        if isinstance(v, IAtom):
            return v.real_value
        else:
            return v

    return map_structure(repl, args)


class Atom(IAtom):
    __slots__ = ("_value", "_memo_value")

    def __init__(self, value: object, memo_value: object):
        """Create Atom: special object that can be included in args/kwargs
        of Group.add. Atom is used to:

        1. explicitly indicate an object being atom.
        2. specify memoized value for the object

        Args:
            value: object to be wrapped.
            memo_value: value used for memoization instead of `value`.

        Example1:

            Wrap a lambda function.

            ```
            g = create_group('root')
            g.add('rule.txt', func, Atom(lambda x: x**2, None))
            g.make()
            ```

            `func(Path("root/rule.txt"), lambda x: x ** 2)` will be executed.
            The lambda function will not be memoized (instead, `None` will be)


        Example2:

            Wrap a numpy array.

            ```
            array = np.array([1,2,3])
            g = create_group('root')
            g.add('rule.txt', method, Atom(array, str(array))
            g.make()
            ```

            `func(Path("root/rule.txt"), np.array([1,2,3])` will be executed.
            Instead of the ndarray object, "[1, 2, 3]" will be memoized.
        """
        self._value = value
        self._memo_value = memo_value

    @property
    def real_value(self):
        return self._value

    @property
    def memo_value(self):
        return self._memo_value

    def __repr__(self):
        v, m = repr(self.real_value), repr(self.memo_value)
        return f"Atom(value={v}, memo_value={m})"


def Mem(arg: object, memo_value: object) -> Any:
    return Atom(arg, memo_value)


def Memstr(arg: object) -> Any:
    """
    Alias for `Atom(arg, str(arg))`.
    Use str(arg) as the value for memoization of arg
    """
    return Atom(arg, str(arg))


def Memnone(arg: object) -> Any:
    """
    Alias for `Atom(arg, "")`.
    Let arg be not memoized.
    """
    return Atom(arg, "")
