from __future__ import annotations
import os
from pathlib import Path

from jtcmake import SELF, GroupOfGroups
from jtcmake.group_tree.groups import GroupOfRules


def write(dst: Path, c: str):
    dst.write_text(c)


def test_GroupOfGroups(tmp_path: Path):
    ggggr = GroupOfGroups(GroupOfGroups[GroupOfGroups[GroupOfRules]], tmp_path)

    for i in range(2):
        gggr = ggggr.add_group(f"sub{i}").init(GroupOfGroups, prefix=f"{i}-")

        for j in range(2):
            ggr = gggr.add_group(f"sub{j}").init(GroupOfRules, prefix=f"{j}-")

            for k in range(2):
                gr = ggr.add_group(f"sub{k}").set_prefix(prefix=f"{k}-")

                for i in range(2):
                    gr.add(f"r{i}", write)(SELF, "a")

    assert os.path.abspath(ggggr.sub0.sub0.sub0.r0[0]) == os.path.abspath(
        tmp_path / "0-0-0-r0"
    )
