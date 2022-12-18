from jtcmake import stringify_dirtree, UntypedGroup, SELF


def test_print_dirtree():
    def fn(_: object):
        ...

    g = UntypedGroup("a")

    g.add("a", fn)(SELF)

    d1 = g.add_group("d1")
    d1.add("a", fn)(SELF)
    d1.add("b", fn)(SELF)

    d2 = g.add_group("d2")
    d2.add("a", fn)(SELF)

    assert (
        stringify_dirtree(g)
        == """\
a/
├── a
├── d1/
│   ├── a
│   └── b
└── d2/
    └── a
"""
    )

    assert (
        stringify_dirtree(g, True)
        == """\
a/
├── a        /a/a
├── d1/
│   ├── a    /d1/a/a
│   └── b    /d1/b/b
└── d2/
    └── a    /d2/a/a
"""
    )
