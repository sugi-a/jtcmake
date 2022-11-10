from pathlib import Path
from typing import Literal
from jtcmake import GroupOfRules, GroupOfGroups, StaticGroupBase, Rule, SELF, VFile

def func1(a: Path):
    ...

def func2(a: Path, b: Path):
    ...


class Static1(StaticGroupBase):
    r1: Rule[str]
    r2: Rule[Literal["a", "b"]]
    g1: GroupOfGroups[GroupOfRules]


    def __init__(self):
        self.r1.init({"a": "a.txt", "b": "b.txt"}, func2)(SELF.a, b=SELF[1])
        self.r1.init(["a.txt", "b.txt"], func2)(SELF[0], SELF[1])
        self.r1.init("a.txt", func1)(SELF)
        self.r1.init(VFile("a.txt"), func1)(SELF)
        self.r2.init({"a": "a.txt", "b": "b.txt"}, func2)(SELF.a, b=SELF[1])
        self.r2.init(Path("x"), func2)(SELF.a, b=SELF[1])

        gr = self.g1.init(GroupOfRules)
        gr.add_group("a")
