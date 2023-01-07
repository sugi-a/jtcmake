from __future__ import annotations

import itertools
import os
from collections import deque
from html import escape
from pathlib import Path
from typing import Literal, Optional, Sequence, Union

from ...core.make import make
from ...logwriter import term_is_jupyter
from ...utils.strpath import StrOrPath
from ..core import IGroup, IRule, get_group_info_of_nodes

CDN_SCRIPT = "https://unpkg.com/mermaid@9.2.2/dist/mermaid.js"
CDN_INTEGRITY = (
    "sha384-eVI7r0LLajhlRTrir+Ocpp+icp4EkgFeCF3EyXLmSTLwO6jC09JTGjCed7tHzLMn"
)

Direction = Literal["LR", "TD"]
GroupTreeNode = Union[IGroup, IRule]


def print_mermaid(
    target_nodes: Union[GroupTreeNode, list[GroupTreeNode]],
    output_file: Optional[StrOrPath] = None,
    max_dependency_depth: int = 1000000,
    direction: Direction = "LR",
    mermaidjs: Optional[str] = CDN_SCRIPT,
):
    """
    Visualizes the structure of a group tree and dependency of its rules using
    *mermaid.js*.

    Example:

        ::

            import shutil
            import jtcmake as jtc

            g = jtc.UntypedGroup("root")
            g.add("a", shutil.copy)(jtc.File("src1.txt"), SELF)
            g.add("b", shutil.copy)(jtc.File("src2.txt"), SELF)
            g.add("c", shutil.copy)(jtc.File("src3.txt"), SELF)

            print_method(g, "graph.html")  # visualize the whole tree
            print_method([g.a, g.c], "graph.html")  # visualize specific nodes
    """
    target_nodes = _parse_args_nodes(target_nodes)
    direction = _parse_args_direction(direction)

    if output_file is None:
        code = gen_mermaid_code(
            target_nodes, None, max_dependency_depth, direction
        )

        if term_is_jupyter():
            from IPython.display import HTML, display  # type: ignore

            html = embed_to_html(code, mermaidjs)
            display(HTML(html))
            return
        else:
            print(code)
            return
    else:
        output_file = Path(output_file)

        data = gen_mermaid_code(
            target_nodes, output_file.parent, max_dependency_depth, direction
        )

        if output_file.suffix in (".html", ".htm"):
            data = embed_to_html(data, mermaidjs)

        output_file.write_text(data)


def embed_to_html(
    code: str,
    mermaidjs: Optional[str] = CDN_SCRIPT,
) -> str:
    if mermaidjs is None:
        script = (
            f'<script src="{CDN_SCRIPT}" integrity="{CDN_INTEGRITY}"></script>'
        )
    else:
        script = f'<script src="{mermaidjs}"></script>'

    return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>graph</title></head>
        <body>
            <pre class="mermaid">{code}</pre>
            {script}
            <script>mermaid.initialize({{ startOnLoad: true }}); </script>
        </body>
        </html>
        """


def escape2(s: str) -> str:
    return escape(escape(s))


def collect_targets(
    root: IGroup,
    explicit_targets: Sequence[GroupTreeNode],
    max_dependency_depth: int,
) -> tuple[dict[IGroup, str], dict[IRule, str], dict[str, str], set[str]]:
    gid: dict[IGroup, str] = {}
    rid: dict[IRule, str] = {}
    fid: dict[str, str] = {}

    def collect_node(node: GroupTreeNode, recursive: bool):
        if isinstance(node, IGroup):
            collect_group(node, recursive)
        else:
            assert isinstance(node, IRule)
            collect_rules(node, recursive)

    def collect_group(g: IGroup, recursive: bool):
        if g in gid:
            return

        gid[g] = f"cluster_g{len(gid)}"

        if recursive:
            for child in itertools.chain(g.groups.values(), g.rules.values()):
                collect_node(child, True)

    def collect_rules(r: IRule, recursive: bool):
        if r in rid:
            return

        rid[r] = f"cluster_r{len(rid)}"

        if recursive:
            for yf in r.files.values():
                collect_file(os.path.abspath(yf))

    def collect_file(f: str):
        if f not in fid:
            fid[f] = f"f{len(fid)}"

    for node in explicit_targets:
        collect_node(node, True)

    explicit_ids = set(
        itertools.chain(gid.values(), rid.values(), fid.values())
    )

    # get dependencies by BFS
    visited: set[IRule] = set()
    q: deque[tuple[int, IRule]] = deque((0, r) for r in rid)

    while q:
        depth, r = q.popleft()

        if r in visited:
            continue

        visited.add(r)

        if depth >= max_dependency_depth:
            continue

        for xf in r.xfiles:
            xf = os.path.abspath(xf)
            collect_file(xf)
            depr = get_rule_of_f(root, xf)
            if depr is not None:
                q.append((depth + 1, depr))

    visited2: set[GroupTreeNode] = set()

    for r in visited:
        node = r
        while True:
            collect_node(node, False)
            node = node.parent

            if node in visited2:
                break

            visited2.add(node)

    return gid, rid, fid, explicit_ids


def gen_mermaid_code(
    target_nodes: Sequence[GroupTreeNode],
    basedir: Optional[StrOrPath],
    max_dependency_depth: int,
    direction: Direction,
) -> str:
    info = get_group_info_of_nodes(target_nodes)

    res: list[tuple[int, str]] = []  # (indent, line)[]

    gid, rid, fid, explicit_nodes = collect_targets(
        info.root, target_nodes, max_dependency_depth
    )

    make_summary = make(
        info.rule_store.rules,
        [r.raw_rule_id for r in rid],
        dry_run=True,
        keep_going=True,
        callback=lambda _: None,
    )

    res.append((0, f"flowchart {direction}"))

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

        label = f"{name} ({prefix})"
        res.append((idt, f'subgraph {gid[g]}["{escape2(label)}"]'))

        for child_group in g.groups.values():
            gen_group(child_group, idt + 1)

        for name, child_rule in g.rules.items():
            gen_rule(child_rule, idt + 1)

        res.append((idt, "end"))

    def gen_rule(r: IRule, idt: int):
        if r not in rid:
            return

        label = r.name_tuple[-1]

        res.append((idt, f"subgraph {rid[r]}[{escape2(label)}]"))

        par_prefix = os.path.abspath(r.parent.prefix + "_")[:-1]

        for yf in r.files.values():
            gen_file(os.path.abspath(yf), par_prefix, idt + 1)

        res.append((idt, "end"))

    def gen_file(f: str, par_prefix: str, idt: int):
        if f not in fid:
            return

        if par_prefix != "" and f[: len(par_prefix)] == par_prefix:
            p = "... " + f[len(par_prefix) :]
        else:
            p = _relpath(f, basedir)

        res.append((idt + 1, f"{fid[f]}[{escape2(p)}]"))

    gen_group(info.root, 1)

    # define original files node
    for f in fid:
        if info.rule_store.ypath2idx[f] == -1:
            gen_file(f, "", 2)

    # define arrows
    for r, id in rid.items():
        for xf in r.xfiles:
            xf = os.path.abspath(xf)
            if xf in fid:
                res.append((1, f"{fid[xf]}-->{id}"))

    # define links
    for f, id in fid.items():
        res.append((1, f'click {id} "{escape(_relpath(f, basedir))}" _blank'))

    # define styles
    for id in rid.values():
        res.append((1, f"style {id} fill:#feb"))

    for id in implicit_nodes:
        res.append((1, f"style {id} stroke-dasharray: 5 5"))

    for f, id in fid.items():
        if os.path.exists(f):
            rule_id = info.rule_store.ypath2idx[f]
            if rule_id == -1 or make_summary.detail[rule_id] == "skip":
                res.append((1, f"style {id} fill:#{COLOR_BLUE}"))
            else:
                res.append((1, f"style {id} fill:#{COLOR_YELLOW}"))
        else:
            res.append((1, f"style {id} fill:#{COLOR_RED}"))

    return "\n".join("  " * idt + line for idt, line in res) + "\n"


COLOR_RED = "ffadad"
COLOR_BLUE = "caffbf"
COLOR_YELLOW = "ffd6a5"


def _assert_node_list(nodes: object) -> list[GroupTreeNode]:
    if isinstance(nodes, (list, tuple)):
        for node in nodes:  # pyright: ignore [reportUnknownVariableType]
            if not isinstance(node, (IGroup, IRule)):
                raise TypeError(f"node must be rule or group. Given {node}")

        return list(nodes)
    else:
        raise TypeError("nodes must be rule or group or list of them")


def _parse_args_nodes(nodes: object) -> list[GroupTreeNode]:
    if isinstance(nodes, (IGroup, IRule)):
        return [nodes]
    else:
        return _assert_node_list(nodes)


def _parse_args_direction(direction: object) -> Direction:
    if direction not in ("LR", "TD"):
        raise ValueError("direction must be 'LR' or 'TD'")

    return direction


def _relpath(p: StrOrPath, basedir: Optional[StrOrPath]) -> str:
    basedir = basedir or os.getcwd()

    try:
        if isinstance(p, str):
            # trick to preserve the trailing "/"
            return os.path.relpath(p + "_", basedir)[:-1]
        else:
            return os.path.relpath(p, basedir)
    except Exception:
        pass

    return str(p)


def get_rule_of_f(root: IGroup, f: str) -> Optional[IRule]:
    info = root._get_info()  # pyright: ignore [reportPrivateUsage]
    rule_store = info.rule_store
    idx = rule_store.ypath2idx[f]
    if idx == -1:
        return None

    *par_names, basename = rule_store.idx2name[idx]

    for name in par_names:
        root = root.groups[name]

    return root.rules[basename]
