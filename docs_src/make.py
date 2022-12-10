from __future__ import annotations
import inspect
import sys
from pathlib import Path
from subprocess import run
from argparse import ArgumentParser
from typing import Callable

from jtcmake import RulesGroup, SELF


def shell(cmd: str):
    sys.stderr.write("cmd: " + cmd + "\n")
    assert run(cmd, shell=True).returncode == 0


def autoself(f: Callable[[], object]) -> Callable[[], object]:
    params = inspect.signature(f).parameters
    kwargs = {k: v.default for k, v in params.items()}
    assert all(v is not inspect.Parameter.empty for v in kwargs.values())

    def method(slf: Path = SELF, kwargs: dict[str, object] = kwargs):
        f(**kwargs)
        slf.touch()

    return method


g = RulesGroup(prefix="tmp-")

@g.add_deco("example_hello", noskip=True)
@autoself
def example_hello():
    shell("cd source/example_hello && python make.py")


@g.add_deco("example_c_build", noskip=True)
@autoself
def example_c_build():
    shell("cd source/example_c_build && python _make_resources.py")


@g.add_deco("figure_group_tree", noskip=True)
@autoself
def figure_group_tree():
    shell("cd source/figure_group_tree && python draw.py")


@g.add_deco("html", noskip=True)
@autoself
def html(_ = [g.example_c_build, g.example_hello, g.figure_group_tree]):
    shell("sphinx-build -b html ./source ../docs")
    shell("touch ../docs/.nojekyll")


@g.add_deco("doctest", noskip=True)
@autoself
def doctest():
    shell("sphinx-build -b doctest ./source ../tmp-sphinx-doctest")
    

def main():
    p = ArgumentParser()
    p.add_argument("target", choices=g.rules.keys())
    args = p.parse_args()
    g[args.target].make(njobs=2)


if __name__ == "__main__":
    main()
