from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Union, Sequence

from jtcmake import StaticGroupBase, Rule, RulesGroup, SELF, VFile, make

SRCDIR_LIBA = Path(__file__).parent / "src/liba"
SRCDIR_LIBB = Path(__file__).parent / "src/libb"
SRCDIR_TOOL = Path(__file__).parent / "src/tools"

SRC_NAMES_LIBA = [ "a1.c", "a2.c", "a3.c" ]
SRC_NAMES_LIBB = [ "b1.c", "b2.c", "b3.c" ]
SRC_NAMES_TOOL = ["tool1.c", "tool2.c", "tool3.c", "tool4.c", "tool5.c"]

# Create value file instances of the source files
srcs_liba = [VFile(SRCDIR_LIBA / basename) for basename in SRC_NAMES_LIBA]
srcs_libb = [VFile(SRCDIR_LIBB / basename) for basename in SRC_NAMES_LIBB]
srcs_tool = [VFile(SRCDIR_TOOL / basename) for basename in SRC_NAMES_TOOL]


def shell(*cmd_fragments: Union[Path, str]):
    """Run shell script"""
    cmd = " ".join(map(str, cmd_fragments))
    p = subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr)
    if p.returncode != 0:
        raise Exception(f"{cmd} failed with code {p.returncode}")


class StaticLibrary(StaticGroupBase):
    # Take library source files and output a static library file

    objects: RulesGroup  # object files like xxx.o
    library: Rule[str]  # libyyy.a

    def init(self, libname: str, srcs: Sequence[Path]) -> StaticLibrary:
        # Compile C codes into object files
        for src in srcs:
            self.objects.addvf(src.stem, "<R>.o", shell)("gcc -c -o", SELF, src)

        objs = [rule[0] for rule in self.objects.rules.values()]

        # Archive the object files into a static library
        self.library.initvf(f"lib{libname}.a", shell)("ar rv", SELF, *objs)

        return self
        

class Main(StaticGroupBase):
    liba: StaticLibrary
    libb: StaticLibrary
    tools: RulesGroup  # Executables

    def init(self) -> Main:
        self.liba.set_prefix("libs").init("a", srcs_liba)
        self.libb.set_prefix("libs").init("b", srcs_libb)

        # Compile and link the tools and generate executables
        for src in srcs_tool:
            self.tools.addvf(src.stem, shell)(
                "gcc -o",
                SELF,
                f"-I{SRCDIR_LIBA} -I{SRCDIR_LIBB}",
                src,
                self.liba.library[0],
                self.libb.library[0],
            )

        return self


if __name__ == "__main__":
    g = Main(Path(__file__).parent / "out").init()

    # Glob pattern to specify the nodes to make
    pattern = sys.argv[1] if len(sys.argv) >= 2 else "**"

    make(*g.select_rules(pattern), *g.select_groups(pattern))
