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
    shell("cd source/example_c_build && python _make_resources.py")

@add
def figure_group_tree():
    shell("cd source/figure_group_tree && python draw.py")


@add
def html():
    tasks["example_c_build"]()
    tasks["example_hello"]()
    tasks["figure_group_tree"]()
    shell("sphinx-build -b html ./source ../docs")
    shell("touch ../docs/.nojekyll")


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
