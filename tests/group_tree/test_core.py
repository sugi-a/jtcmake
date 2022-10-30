# type: ignore

import os
from pathlib import Path

import pytest

from jtcmake.group_tree.core import (
    parse_args_prefix,
    concat_prefix
)


@pytest.mark.parametrize("dirname,prefix,expect", [
    (None, "a", "a"),
    (None, Path("a"), "a"),
    ("a", None, "a" + os.path.sep),
    (Path("a"), None, "a" + os.path.sep),
    ("a", "a", TypeError),
])
def test_parse_args_prefix(dirname, prefix, expect):
    if isinstance(expect, str):
        assert parse_args_prefix(dirname, prefix) == expect
    else:
        with pytest.raises(expect):
            parse_args_prefix(dirname, prefix)


@pytest.mark.parametrize("base,prefix,expect", [
    ("a", "b", "ba"),
    (os.path.abspath("a"), "b", os.path.abspath("a")),
    ("~/a", "b", os.path.expanduser("~/a")),
])
def test_concat_prefix(base, prefix, expect):
    concat_prefix(base, prefix) == expect



