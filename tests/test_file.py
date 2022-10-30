import hashlib, base64

from jtcmake.rule.file import get_hash


def test_vfile_hash(tmp_path):
    p = tmp_path / "a"
    p.write_text("a")

    assert get_hash(p) == base64.b64encode(hashlib.md5(b"a").digest()).decode()
