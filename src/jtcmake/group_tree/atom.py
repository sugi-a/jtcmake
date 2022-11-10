from typing import Any
from ..memo.abc import IMemoAtom


class Atom(IMemoAtom):
    def __init__(self, value: Any, memo_value: Any):
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
        self.value = value
        self._memo_value = memo_value

    @property
    def memo_value(self):
        return self._memo_value

    def __repr__(self):
        v, m = repr(self.value), repr(self._memo_value)
        return f"Atom(value={v}, memo_value={m})"


def Memstr(arg: object) -> Atom:
    """
    Alias for `Atom(arg, str(arg))`.
    Use str(arg) as the value for memoization of arg
    """
    return Atom(arg, str(arg))


def Nomem(arg: object) -> Atom:
    """
    Alias for `Atom(arg, "")`.
    Let arg be not memoized.
    """
    return Atom(arg, "")
