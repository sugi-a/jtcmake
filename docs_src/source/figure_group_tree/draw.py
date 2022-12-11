from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass
import subprocess
from html import escape

@dataclass
class Node:
    attrs: dict[str, str]
    cs: list[Node]
    kind: str
    shape: str

def Group(name: str, prefix: str, cs: list[Node]):
    return Node(
        {"basename": name, "path-prefix": prefix}, cs, "Group", "ellipse"
    )


def Rule(name: str, cs: list[Node]):
    return Node({"basename": name}, cs, "Rule", "hexagon")


def File(name: str, base: str):
    return Node({"basename": name, "path-base": base}, [], "File", "box")


FONTNAME = "sans-serif"

def _gen_node(_id: Callable[[Node], str], res: list[str], n: Node):
    def _escape(v: str):
        if v == "<ROOT>":
            return f'{escape(v)}'
        else:
            return f'"{v}"'

    lab = f'<B>{n.kind}</B><BR/>' \
        + "".join(f'{k} = {_escape(v)}<BR/>' for k, v in n.attrs.items())

    res.append(
        f'{_id(n)} ['
        + f' nojustify=true label=<{lab}>'
        + f' fontname="{FONTNAME}"'
        + f' shape="{n.shape}"'
        + "]"
    )
    for c in n.cs:
        _gen_node(_id, res, c)
        res.append(f'{_id(n)} -- {_id(c)}')
    
        
def gen_dot(root: Node) -> str:
    res: list[str] = []

    def _id(n: Node) -> str:
        return f'n{id(n)}'

    res.append("graph {")
    _gen_node(_id, res, root)
    res.append("}")
    
    return "\n".join(res)


def _get_files(
    root: Node,
    name: str = "",
    prefix: str = "",
    res: Optional[list[tuple[str, str]]] = None
) -> list[tuple[str, str]]:
    if res is None:
        res = []

    if root.kind == "File":
        res.append((
            name + f".{root.attrs['basename']}",
            prefix + root.attrs["path-base"])
        )
    else:
        for c in root.cs:
            _get_files(
                c,
                name + f".{root.attrs['basename']}",
                prefix + (root.attrs.get("path-prefix", "")),
                res,
            )

    return res


def gen_file_table(files: list[tuple[str, str]]) -> str:
    files = [(".Name", "Path"), *files]
    w = 4 + max(len(name) for name, _ in files)
    return "\n".join(
        name[1:] + " " * (w - len(name))  + path for name, path in files
    )


G = Group("<ROOT>", "top/", [
    Group("foot", "foo-", [
        Rule("a", [
            File("f1", "f1.txt"),
            File("f2", "f2.txt")
        ]),
        Rule("b", [File("f3", "f3.txt")]),
    ]),
    Group("bar", "", [
        Group("baz1", "baz/", [Rule("c", [File("x", "y")])]),
        Group("baz2", "baz/", [Rule("c", [File("p", "q")])]),
        Rule("c", [File("p", "q")]),
    ]),
])

def main():
    code = gen_dot(G)
    assert subprocess.run(
        ["dot", "-Tsvg", "-otmp-group-tree.svg"], input=code.encode(),
    ).returncode == 0

    files_txt = gen_file_table(_get_files(G))
    Path("tmp-files.txt").write_text(files_txt)

if __name__ == "__main__":
    main()
