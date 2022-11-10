from logging import getLogger

import pytest

from jtcmake.logwriter import (
    ColorTextWriter,
    HTMLFileWriterOpenOnDemand,
    LoggerWriter,
    TextFileWriterOpenOnDemand,
    TextWriter,
)
from jtcmake.group_tree.group_mixins import basic


class Path_:
    def __init__(self, p: str):
        self.p = p

    def __fspath__(self) -> str:
        return self.p


class Writable:
    def write(self, s: str):
        del s


class WritableTTY:
    def write(self, s: str):
        del s

    def isatty(self) -> bool:
        return True


def test_create_logwriter():
    loglevel = "info"

    w = basic.create_logwriter("a.log", loglevel)
    assert isinstance(w, TextFileWriterOpenOnDemand)

    w = basic.create_logwriter("a.html", loglevel)
    assert isinstance(w, HTMLFileWriterOpenOnDemand)

    w = basic.create_logwriter(Path_("a.html"), loglevel)
    assert isinstance(w, HTMLFileWriterOpenOnDemand)

    w = basic.create_logwriter(getLogger("a"), loglevel)
    assert isinstance(w, LoggerWriter)

    w = basic.create_logwriter(Writable(), loglevel)
    assert isinstance(w, TextWriter)

    w = basic.create_logwriter(WritableTTY(), loglevel)
    assert isinstance(w, ColorTextWriter)

    with pytest.raises(TypeError):
        basic.create_logwriter(None, loglevel)
