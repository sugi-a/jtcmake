import pytest
from jtcmake import StaticGroupBase, Rule


class Group(StaticGroupBase):
    a: Rule[str]


def test_guard_outputless_rule():
    g = Group()

    def _f():
        ...

    with pytest.raises(ValueError):
        g.a.init({}, _f)()
