from jtcmake.group_tree.atom import Atom
from jtcmake.rule.memo.abc import IMemoAtom


def test_atom():
    a = Atom(1, 2)

    assert a.memo_value == 2


def test_atom_type():
    assert issubclass(Atom, IMemoAtom)
