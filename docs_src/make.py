import sys
from pathlib import Path
from subprocess import run
from argparse import ArgumentParser
from typing import Callable

tasks = {}

def add(f: Callable[..., object]):
    tasks[f.__name__] = f

def shell(cmd: str):
    sys.stderr.write("cmd: " + cmd + "\n")
    assert run(cmd, shell=True).returncode == 0


@add
def example_hello():
    shell("cd source/example_hello && python make.py")


@add
def example_c_build():
    from jtcmake import print_graphviz
    from source.example_c_build.make import g

    d = Path("./source/example_c_build")
    print_graphviz(g, d / "_tmp-graph-all.svg")
    print_graphviz(g.tools.tool1, d / "_tmp-graph-tool1.svg")
    print_graphviz(g.liba, d / "_tmp-graph-liba.svg")

    shell(f"rm -rf {d}/out")
    shell(f"cd {d} && tree --noreport -I '_*' > _tmp-tree-all.txt")

    g.liba.make()
    shell(f"cd {d} && tree --noreport ./out > _tmp-tree-liba.txt")

    g.make()
    shell(f"cd {d} && tree --noreport ./out > _tmp-tree-out.txt")


@add
def html():
    tasks["example_c_build"]()
    tasks["example_hello"]()
    shell("sphinx-build -b html ./source ../docs")


@add
def doctest():
    shell("sphinx-build -b doctest ./source ../tmp-sphinx-doctest")
    

def main():
    p = ArgumentParser()
    p.add_argument("target", choices=tasks.keys())
    args = p.parse_args()
    tasks[args.target]()

if __name__ == "__main__":
    main()
