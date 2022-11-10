# type: ignore

from pathlib import Path

import pytest

from jtcmake import UntypedGroup, SELF


def write(p: Path, c: str):
    p.write_text(c)


def test_basic(tmp_path: Path):
    g = UntypedGroup(tmp_path)

    g.add("a", write)(SELF, "a")

    g.add_group("sub").add("b", write)(SELF, "b")

    g.make()

    assert g.a[0].read_text() == "a"
    assert g.sub.b[0].read_text() == "b"


def test_error_on_dupe_registration():
    # rule -> group
    g = UntypedGroup()
    g.add("a", write)(SELF, "a")
    with pytest.raises(KeyError):
        g.add_group("a")

    # group -> rule
    g = UntypedGroup()
    g.add_group("a")
    with pytest.raises(KeyError):
        g.add("a", write)(SELF, "a")
