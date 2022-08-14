import os, hashlib, base64
import pytest

from jtcmake.rule.file import IFile, IVFile, File, VFile


def test_file(tmp_path):
    p = tmp_path / 'a'
    f = File(p)

    assert f.path == p


def test_vfile(tmp_path):
    p = tmp_path / 'a'
    f = VFile(p)

    f.path.write_text('a')

    assert f.get_hash() == base64.b64encode(hashlib.md5(b'a').digest()).decode()
    assert f.get_hash() == base64.b64encode(hashlib.md5(b'a').digest()).decode()
