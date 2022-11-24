import sys
import shutil
from pathlib import Path
from subprocess import run

from jtcmake import print_graphviz
from make import Main

def shell(cmd: str):
    sys.stderr.write("cmd: " + cmd + "\n")
    assert run(cmd, shell=True).returncode == 0


g = Main(Path(__file__).parent / "out").init()

print_graphviz(g, "_tmp-graph-all.svg")
print_graphviz(g.tools.tool1, "_tmp-graph-tool1.svg")
print_graphviz(g.liba, "_tmp-graph-liba.svg")

shell("rm -rf out && mkdir out")
shell("tree --noreport -I '_*' > _tmp-tree-all.txt")

g.liba.make()
shell(f"tree --noreport ./out > _tmp-tree-liba.txt")

g.make()
shell(f"tree --noreport ./out > _tmp-tree-out.txt")

g = Main(Path(__file__).parent / "out", logfile="_tmp-log.txt").init()
g.clean()
shell("rm _tmp-log.txt")
g.liba.make(dry_run=True)
