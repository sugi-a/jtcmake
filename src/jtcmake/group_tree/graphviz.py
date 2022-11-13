import os
import sys
import shutil
import subprocess
from html import escape
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from typing_extensions import TypeAlias

from .core import IGroup, IRule
from ..logwriter import term_is_jupyter

StrOrPath: TypeAlias = "Union[str, os.PathLike[str]]"

RankDir = Literal["TD", "LR"]


def print_graphviz(
    group: IGroup,
    output_file: Optional[StrOrPath] = None,
    *,
    rankdir: RankDir = "LR",
):
    """Visualize the dependency graph using Graphviz
    Args:
        group (Group): Group node whose Rules will be visualized
        output_file (str|os.PathLike|None):
            If specified, graph will be written into the file.
            Otherwise, graph will be printed to the terminal (available on
            Jupyter only). Graph format depends on the file extension:

            - .svg: SVG
            - .htm or .html: HTML (SVG image embedded)
            - .dot: Graphviz's DOT code (text)
    """
    if output_file is None:
        if term_is_jupyter():
            from IPython.display import display, SVG  # type: ignore

            dot_code = gen_dot_code(group, rankdir=rankdir)
            svg = convert(dot_code, "svg").decode()
            display(SVG(svg))
            return
        else:
            raise Exception("Printing to console is available on Jupyter only")
    else:
        assert isinstance(output_file, (str, os.PathLike))
        output_file = str(output_file)

        dot_code = gen_dot_code(
            group, Path(output_file).parent, rankdir=rankdir
        )

        if output_file[-4:] == ".svg":
            data = convert(dot_code, "svg")
        elif output_file[-4:] == ".dot":
            data = dot_code.encode()
        elif output_file[-4:] == ".htm" or output_file[-5:] == ".html":
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
    group: IGroup, basedir: Optional[StrOrPath] = None, rankdir: RankDir = "LR"
):
    if not isinstance(
        group, IGroup
    ):  # pyright: ignore [reportUnnecessaryIsInstance]
        raise TypeError("argument group must be Group")

    if rankdir not in {"TB", "LR"}:
        raise ValueError(f"rankdir must be TB or LR. Given: {rankdir}")

    gid: Dict[IGroup, int] = {}
    rid: Dict[IRule, int] = {}
    fid: Dict[str, int] = {}

    res: List[str] = []
    res.append("digraph {")
    res.append("  compound=true;")
    res.append(f"  rankdir={rankdir};")

    def rec_group(g: IGroup, idt: str, par_prefix: str):
        gid[g] = len(gid)

        name = "<ROOT>" if len(g.name_tuple) == 0 else g.name_tuple[-1]

        if par_prefix == "":
            prefix = g.prefix
        elif g.prefix[: len(par_prefix)] == par_prefix:
            prefix = "... " + g.prefix[len(par_prefix) :]
        else:
            prefix = g.prefix

        res.append(idt + f"subgraph cluster{gid[g]} {{")
        res.append(
            idt + f"  label = <<B>{escape(name)}</B> "
            f'(<FONT FACE="monospace">{escape(prefix)}</FONT>)>;'
        )
        res.append(idt + '  style = "rounded";')

        for child_group in g.groups.values():
            rec_group(child_group, idt + "  ", g.prefix)

        for name, child_rule in g.rules.items():
            proc_rulew(child_rule, name, idt + "  ", g.prefix)

        res.append(idt + "};")

    def proc_rulew(r: IRule, name: str, idt: str, par_prefix: str):
        rid[r] = len(rid)

        res.append(idt + f"subgraph cluster_r_{rid[r]} {{")
        res.append(idt + f"  label=<<B>{escape(name)}</B>>;")
        res.append(idt + '  bgcolor = "#E0FFFF";')

        par_prefix = os.path.abspath(par_prefix + "_")[:-1]

        for yf in r.files.values():
            fid[os.path.abspath(yf)] = len(fid)

            p = os.path.abspath(yf)
            if par_prefix != "" and p[: len(par_prefix)] == par_prefix:
                p = "... " + p[len(par_prefix) :]
            else:
                p = str(yf)

            res.append(
                idt + f"  f{fid[os.path.abspath(yf)]} ["
                f'label=<<FONT FACE="monospace">{escape(p)}</FONT>>; '
                f"style=filled; "
                f"color=white; "
                f"shape=plain; "
                f'margin="0.1,0.1"; '
                f'URL="{_mk_link(yf, basedir)}"; '
                f"];"
            )
        res.append(idt + "}")

    rec_group(group, "  ", "")

    for r in rid.keys():
        f0 = os.path.abspath(next(iter(r.files.values())))
        for xf in r.xfiles:
            if xf not in fid:
                fid[xf] = len(fid)
                res.append(
                    f"  f{fid[xf]} ["
                    f'label=<<FONT FACE="monospace">'
                    f"{escape(str(xf))}</FONT>>; "
                    f"shape=plain; "
                    f'URL="{_mk_link(xf, basedir)}"; '
                    f"];"
                )

            res.append(
                f"  f{fid[xf]} -> f{fid[f0]} " f"[lhead=cluster_r_{rid[r]}];"
            )

    res.append("}")

    return "\n".join(res) + "\n"


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


def _mk_link(p: StrOrPath, basedir: Optional[StrOrPath]) -> str:
    basedir = basedir or os.getcwd()

    try:
        return os.path.relpath(p, basedir)
    except Exception:
        pass

    return str(p)
