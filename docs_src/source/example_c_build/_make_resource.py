import subprocess

from jtcmake import print_graphviz
from make import g

print_graphviz(g, "_tmp-graph-all.svg")
print_graphviz(g.tools.tool1, "_tmp-graph-tool1.svg")
print_graphviz(g.liba, "_tmp-graph-liba.svg")


with open("_tmp-tree-all.txt", "w") as f:
    subprocess.run(["tree", "-I", "_*"], stdout=f)

with open("_tmp-tree-out.txt", "w") as f:
    subprocess.run(["tree", "out"], stdout=f)

