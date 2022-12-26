from __future__ import annotations
import os
import sys
import shutil
import itertools
import subprocess
from html import escape
from pathlib import Path
from typing import Literal, Optional, Sequence, Union

from typing_extensions import TypeAlias

from ...core.make import make
from ..core import IGroup, IRule, get_group_info_of_nodes
from ...logwriter import term_is_jupyter
from .mermaid import (
    collect_targets,
    GroupTreeNode,
    _relpath,  # pyright: ignore [reportPrivateUsage]
    _parse_args_nodes,  # pyright: ignore [reportPrivateUsage]
)

StrOrPath: TypeAlias = "Union[str, os.PathLike[str]]"

RankDir = Literal["TD", "LR"]


def print_graphviz(
    target_nodes: Union[GroupTreeNode, list[GroupTreeNode]],
    output_file: Optional[StrOrPath] = None,
    max_dependency_depth: int = 1000000,
    *,
    rankdir: RankDir = "LR",
):
    """
    Visualize the dependency graph using Graphviz.
    Graphviz binaries are required to be available in PATH.

    Args:
        group: Group node whose Rules will be visualized
        output_file:
            If specified, graph will be written into the file.
            Otherwise, graph will be printed to the terminal (available on
            Jupyter only). Graph format depends on the file extension:

            - .svg: SVG
            - .htm or .html: HTML (SVG image embedded)
            - .dot: Graphviz's DOT code (text)
    """
    target_nodes = _parse_args_nodes(target_nodes)

    if output_file is None:
        dot_code = gen_dot_code(
            target_nodes, None, max_dependency_depth, rankdir=rankdir
        )

        if term_is_jupyter():
            from IPython.display import display, SVG  # type: ignore

            svg = convert(dot_code, "svg").decode()
            display(SVG(svg))
            return
        else:
            print(dot_code)
    else:
        output_file = Path(output_file)

        dot_code = gen_dot_code(
            target_nodes,
            output_file.parent,
            max_dependency_depth,
            rankdir=rankdir,
        )

        if output_file.suffix == ".svg":
            data = convert(dot_code, "svg")
        elif output_file.suffix == ".dot":
            data = dot_code.encode()
        elif output_file.suffix in (".htm", ".html"):
            data = convert(dot_code, "svg").decode()
            data = (
                '<!DOCTYPE html><html><head><meta charset="utf-8">'
                f"<title>graph</title></head><body>{data}</body></html>"
            )
            data = data.encode("utf8")
        else:
            raise ValueError(
                "Output file's extension must be .svg, .dot, .htm, or .html"
            )

        with open(output_file, "wb") as f:
            f.write(data)


def gen_dot_code(
    target_nodes: Sequence[GroupTreeNode],
    basedir: Optional[StrOrPath] = None,
    max_dependency_depth: int = 1000000,
    rankdir: RankDir = "LR",
):
    info = get_group_info_of_nodes(target_nodes)

    res: list[tuple[int, str]] = []

    res.append((0, "digraph {"))
    res.append((1, "compound=true;"))
    res.append((1, f"rankdir={rankdir};"))

    gid, rid, fid, explicit_nodes = collect_targets(
        info.root, target_nodes, max_dependency_depth
    )

    make_results = make(
        info.rule_store.rules,
        [r.raw_rule_id for r in rid],
        dry_run=True,
        keep_going=True,
        callback=lambda _: None,
    ).detail

    implicit_nodes = (
        set(itertools.chain(gid.values(), rid.values())) - explicit_nodes
    )

    def gen_group(g: IGroup, idt: int):
        if g not in gid:
            return

        name = "<ROOT>" if len(g.name_tuple) == 0 else g.name_tuple[-1]

        if g is info.root or g.parent.prefix == "":
            prefix = _relpath(g.prefix, basedir)
        elif g.prefix[: len(g.parent.prefix)] == g.parent.prefix:
            prefix = "... " + g.prefix[len(g.parent.prefix) :]
        else:
            prefix = _relpath(g.prefix, basedir)

        res.append((idt, f"subgraph {gid[g]} {{"))
        res.append(
            (
                idt + 1,
                f"label = <<B>{escape(name)} </B> ( {escape(prefix)} )>;",
            )
        )
        res.append((idt + 1, 'fontname = "sans-serif";'))
        style = "dashed" if gid[g] in implicit_nodes else "solid"
        res.append((idt + 1, f'style = "{style}";'))
        res.append((idt + 1, 'bgcolor = "#FEFAE0";'))
        res.append((idt + 1, 'color = "#d4a373";'))

        for child_group in g.groups.values():
            gen_group(child_group, idt + 1)

        for name, child_rule in g.rules.items():
            gen_rule(child_rule, idt + 1)

        res.append((idt, "};"))

    def gen_rule(r: IRule, idt: int):
        if r not in rid:
            return

        res.append((idt, f"subgraph {rid[r]} {{"))
        res.append((idt + 1, f"label=<<B>{escape(r.name_tuple[-1])}</B>>;"))
        style = "dashed" if rid[r] in implicit_nodes else "solid"
        res.append((idt + 1, f'style = "{style}";'))
        res.append((idt + 1, 'bgcolor = "#faedcd";'))
        res.append((idt + 1, 'color = "#d4a373";'))

        par_prefix = os.path.abspath(r.parent.prefix + "_")[:-1]

        for yf in r.files.values():
            gen_file(os.path.abspath(yf), par_prefix, idt + 1)

        res.append((idt, "}"))

    def gen_file(f: str, par_prefix: str, idt: int):
        if f not in fid:
            return

        if par_prefix != "" and f[: len(par_prefix)] == par_prefix:
            p = "... " + f[len(par_prefix) :]
        else:
            p = _relpath(f, basedir)

        if os.path.exists(f):
            rule_id = info.rule_store.ypath2idx[f]
            if rule_id == -1 or make_results[rule_id] == "skip":
                color = COLOR_BLUE
            else:
                color = COLOR_YELLOW
        else:
            color = COLOR_RED

        res.append(
            (
                idt,
                f"{fid[f]} ["
                f'label="{escape(p)}"; '
                f'fontname="sans-serif"; '
                f'style="filled"; '
                f"shape=box; "
                f'fillcolor="#{color}"; '
                'color = "#d4a373";'
                f'URL="{_relpath(f, basedir)}"; '
                f"];",
            )
        )

    gen_group(info.root, 1)

    # define original file nodes
    for f in fid:
        if info.rule_store.ypath2idx[f] == -1:
            gen_file(f, "", 2)

    # define arrows
    for r in rid.keys():
        f0 = os.path.abspath(next(iter(r.files.values())))
        for xf in r.xfiles:
            xf = os.path.abspath(xf)
            if xf in fid:
                res.append((1, f"{fid[xf]} -> {fid[f0]} [lhead={rid[r]}];"))

    res.append((0, "}"))

    return "\n".join("  " * idt + line for idt, line in res) + "\n"


COLOR_RED = "ffadad"
COLOR_BLUE = "caffbf"
COLOR_YELLOW = "ffd6a5"


def convert(dot_code: str, t: str = "svg"):
    if shutil.which("dot") is None:
        raise Exception(
            "Graphviz is required. dot executable was not found in PATH."
        )

    p = subprocess.run(
        ["dot", f"-T{t}"],
        input=dot_code.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode())
        raise Exception(
            f"Failed to create graph. dot exit with code {p.returncode}"
        )

    return p.stdout


def save_to_file(dot_code: str, fname: StrOrPath, t: str = "svg"):
    with open(fname, "wb") as f:
        f.write(convert(dot_code, t))
