from __future__ import annotations
import os
from pathlib import Path
from typing import NamedTuple

from jtcmake.logwriter import HTMLFileWriterOpenOnDemand

from ...core.make import make
from ..core import IRule, get_group_info_of_nodes
from ..group_mixins.basic import create_default_logwriter
from ..group_mixins.selector import SelectorMixin
from ..event_logger import tostrs_func_call, RichStr

from typing_extensions import TypeAlias


def print_method(rule: IRule):
    """
    Show how the method of the given rule will be called.
    """
    info = rule._get_info()  # pyright: ignore [reportPrivateUsage]
    raw_rule = info.rule_store.rules[rule.raw_rule_id]
    sl = []
    method = raw_rule.method
    tostrs_func_call(sl, method.method, method.args, method.kwargs)

    a = create_default_logwriter("debug")
    a.debug(*sl)


class FileInfo(NamedTuple):
    path: Path
    name: str
    path_color: tuple[int, int, int] | None = None
    name_color: tuple[int, int, int] | None = None


_Trie: TypeAlias = "dict[str, _Trie | FileInfo]"


def print_dirtree(
    g: SelectorMixin,
    show_name: bool = False,
    output_file: str | os.PathLike[str] | None = None,
    basedir: str | os.PathLike[str] | None = None,
):
    """
    Print the directory tree that the output files of ``g`` spans.

    The color of the file names mean:

    * Green: the file exists and will be skipped when executing "make"
    * Yellow: the file exists but will be updated when executing "make"
    * Red: the file does not exist and will be updated when executing "make"
    """

    strs = _stringify_dirtree(g, show_name, basedir)

    if output_file is None:
        create_default_logwriter("debug").debug(*strs)
    else:
        output_file = Path(output_file)
        if output_file.suffix in (".html", ".htm"):
            HTMLFileWriterOpenOnDemand("debug", output_file).info(*strs)
        else:
            output_file.write_text("".join(strs))


def stringify_dirtree(
    g: SelectorMixin,
    show_name: bool = False,
    basedir: str | os.PathLike[str] | None = None,
):
    """
    Take a group node and return the directory tree that the output files of
    it spans.
    """
    strs = _stringify_dirtree(g, show_name, basedir)
    return "".join(strs)


COLOR_RED = (0xD8, 0x00, 0x0C)
COLOR_BLUE = (0x4F, 0x8A, 0x10)
COLOR_YELLOW = (196, 160, 0)


def _stringify_dirtree(
    g: SelectorMixin,
    show_name: bool = False,
    basedir: str | os.PathLike[str] | None = None,
) -> list[str]:
    if basedir is None:
        basedir = os.getcwd()

    rules = g.select_rules("**/*")

    tri: _Trie = {}

    make_summary = make(
        get_group_info_of_nodes([g]).rule_store.rules,
        [r.raw_rule_id for r in rules],
        dry_run=True,
        keep_going=True,
        callback=lambda _: None,
    )

    for r in rules:
        make_result = make_summary.detail[r.raw_rule_id]

        for k, f in r.files.items():
            try:
                path = Path(os.path.relpath(f, basedir))
            except Exception:
                path = Path(os.path.abspath(f))

            if path.exists():
                if make_result == "skip":
                    color = COLOR_BLUE
                else:
                    color = COLOR_YELLOW
            else:
                color = COLOR_RED

            _trie_add(
                tri,
                path.parts,
                FileInfo(path, r.name + "/" + k, color, color),
            )

    return _trie_tostr(tri, show_name)


def _trie_add(tri: _Trie, path: tuple[str, ...], label: FileInfo):
    if len(path) == 1:
        assert tri.get(path[0]) is None
        tri[path[0]] = label
    else:
        if path[0] not in tri:
            nxt = tri[path[0]] = {}
        else:
            nxt = tri[path[0]]
            assert not isinstance(nxt, FileInfo)

        _trie_add(nxt, path[1:], label)


JOINT0 = "│"
JOINT1 = "├"
JOINT2 = "└"
JOINT3 = "─"


def _trie_tostr(
    tri: _Trie,
    print_name: bool,
    dst: None | list[str] = None,
    depth: None | int = None,
    is_last: None | set[int] = None,
    tree_width: None | int = None,
) -> list[str]:
    if dst is None:
        assert depth is None and is_last is None
        dst, depth, is_last, tree_width = (
            [],
            0,
            set(),
            _calc_trie_str_width(tri),
        )
    else:
        assert (
            depth is not None and is_last is not None and tree_width is not None
        )

    for i, (k, v) in enumerate(sorted(tri.items())):
        if i == len(tri) - 1:
            is_last.add(depth)

        width = 0

        if isinstance(v, FileInfo):
            pathbase = RichStr(k, c=v.path_color, link=v.path)
        else:
            pathbase = k

        if depth == 0:
            dst.append(pathbase)
            width += len(dst[-1])
        else:
            for j in range(1, depth):
                if j in is_last:
                    dst.append("    ")
                else:
                    dst.append(f"{JOINT0}   ")

                width += len(dst[-1])

            if depth in is_last:
                dst.append(f"{JOINT2}{JOINT3}{JOINT3} ")
                dst.append(pathbase)
            else:
                dst.append(f"{JOINT1}{JOINT3}{JOINT3} ")
                dst.append(pathbase)

            width += 4 + len(dst[-1])

        if isinstance(v, FileInfo):
            if print_name:
                name = RichStr(v.name, c=v.name_color)
                dst.append(" " * (tree_width - width + 4))
                dst.append(name)
                dst.append("\n")
            else:
                dst.append("\n")
        else:
            dst.append(f"{os.path.sep}\n")
            _trie_tostr(v, print_name, dst, depth + 1, is_last, tree_width)

    is_last.remove(depth)

    return dst


def _calc_trie_str_width(tri: _Trie) -> int:
    width = 0

    for k, v in tri.items():
        if isinstance(v, FileInfo):
            width = max(width, len(k))
        else:
            width = max(width, _calc_trie_str_width(v) + 4)

    return width
