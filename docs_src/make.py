import sys
from subprocess import run
from pathlib import Path
from jtcmake import VFile, SELF, RulesGroup, make

ROOT = Path(__file__).parent
SRC_DIR = ROOT / "source"
OUT_DIR = ROOT / "../docs"

SOURCES = [VFile(p) for p in SRC_DIR.glob("**/*") if p.is_file() and p.name[0] != "."]

g = RulesGroup(OUT_DIR)

@g.addvf_deco(".nojekyll")
def _(nojekyll: Path = SELF, _: object = SOURCES):
    run(
        ["sphinx-build", "-b", "html", SRC_DIR, nojekyll.parent],
        stderr=sys.stderr
    )
    nojekyll.touch()


make(g)
