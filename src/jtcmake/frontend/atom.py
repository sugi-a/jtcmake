class Atom:
    def __init__(self, value, memo_value):
        """Create Atom: special object that can be included in args/kwargs
        of Group.add. Atom is used to:

        1. explicitly indicate an object being atom.
        2. specify memoized value for the object

        Args:
            value: object to be wrapped.
            memo_value: value used for memoization instead of `value`.
                If callable, `memo_value(value)` will be used for memoization .
                Otherwise, memo_value itself will be used.

        Example1:

            Wrap a lambda function.

            ```
            g = create_group('root')
            g.add('rule.txt', func, Atom(lambda x: x**2, None))
            g.make()
            ```

            `func(Path("root/rule.txt"), lambda x: x ** 2)` will be executed.
            The lambda function will not be memoized (instead, `None` will)


        Example2:

            Wrap a numpy array.

            ```
            g = create_group('root')
            g.add('rule.txt', method, Atom(np.array([1,2,3]), str)
            g.make()
            ```

            `func(Path("root/rule.txt"), np.array([1,2,3])` will be executed.
            Instead of the ndarray object, "[1, 2, 3]" will be memoized.
        """
        self.value = value
        if callable(memo_value):
            self.memo_value = memo_value(value)
        else:
            self.memo_value = memo_value
    
    def __repr__(self):
        v, m = repr(self.value), repr(self.memo_value)
        return f'Atom(value={v}, memo_value={m})'


def Memstr(arg):
    """
    Alias for `Atom(arg, str)`.
    Use str(arg) as the value for memoization of arg
    """
    return Atom(arg, str)
    

def Nomem(arg):
    """
    Alias for `Atom(arg, "")`.
    Let arg be not memoized.
    """
    return Atom(arg, "")
