from pathlib import Path

from jtcmake import SELF, UntypedGroup


def write(p: Path, c: str):
    p.write_text(c)


def test_basic(tmp_path: Path):
    g = UntypedGroup(tmp_path)

    g.add("a", write)(SELF, "a")

    g.add_group("sub").add("b", write)(SELF, "b")

    g.make()

    assert g.a[0].read_text() == "a"
    assert g.sub.b[0].read_text() == "b"
