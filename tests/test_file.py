import os, hashlib, base64
import pytest

from jtcmake.rule.file import File, VFile, get_hash


def test_file(tmp_path):
    p = tmp_path / "a"
    f = File(p)

    assert f.path == p


def test_vfile_hash(tmp_path):
    p = tmp_path / "a"
    p.write_text("a")

    assert get_hash(p) == base64.b64encode(hashlib.md5(b"a").digest()).decode()
