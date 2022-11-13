from __future__ import annotations
import re
from abc import ABCMeta
from typing import List, Optional, Sequence, Literal, TypeVar, Union, Tuple, Any

from ..core import IGroup, IRule, IFile

SelectorKind = Literal["group", "rule", "file"]
SELECTOR_KINDS: Tuple[Literal["group"], Literal["rule"], Literal["file"]] = (
    "group",
    "rule",
    "file",
)

SEP = ";"


def get_offspring_groups(
    root: IGroup, dst: Optional[List[IGroup]] = None
) -> List[IGroup]:
    if dst is None:
        dst = []

    dst.append(root)

    for c in root.groups.values():
        get_offspring_groups(c, dst)

    return dst


T = TypeVar("T", IGroup, IRule, IFile)


class SelectorMixin(IGroup, metaclass=ABCMeta):
    def _select(self, pattern: Sequence[str], kind: SelectorKind) -> List[Any]:
        rxs: List[str] = []

        for p in pattern:
            assert len(p) > 0

            if p.find("**") != -1 and p != "**":
                raise ValueError(
                    'Invalid pattern: "**" can only be an entire component'
                )
            if p == "**":
                rxs.append(f"({SEP}[^{SEP}]+)*")
            else:
                if p == "*":
                    # single * does not match an empty str
                    rxs.append(f"{SEP}[^{SEP}]+")
                else:

                    def _repl(m: re.Match[str]) -> str:
                        x = m.group()
                        return f"[^{SEP}]*" if x == "*" else re.escape(x)

                    p = re.sub(r"\*|[^*]+", _repl, p)
                    rxs.append(f"{SEP}{p}")

        regex = re.compile("^" + "".join(rxs) + "$")

        offspring_groups = get_offspring_groups(self)

        def _search(
            targets: List[T], target_names: List[Tuple[str, ...]]
        ) -> List[T]:
            res: List[T] = []

            for target, target_name in zip(targets, target_names):
                target_name = target_name[len(self.name_tuple) :]
                if regex.match("".join(SEP + n for n in target_name)):
                    res.append(target)

            return res

        if kind == "group":
            target_names = [n.name_tuple for n in offspring_groups]
            return _search(offspring_groups, target_names)
        elif kind == "rule":
            target_rules: List[IRule] = []
            target_names: List[Tuple[str, ...]] = []
            for g in offspring_groups:
                for r in g.rules.values():
                    target_rules.append(r)
                    target_names.append(r.name_tuple)
            return _search(target_rules, target_names)
        elif kind == "file":
            target_files: List[IFile] = []
            target_names: List[Tuple[str, ...]] = []
            for g in offspring_groups:
                for r in g.rules.values():
                    for k, f in r.files.items():
                        target_files.append(f)
                        target_names.append((*r.name_tuple, k))  # optimize?
            return _search(target_files, target_names)
        else:
            raise Exception("unreachable")

    def select_rules(self, pattern: Union[str, Sequence[str]]) -> List[IRule]:
        return self._select(_parse_args_pattern(pattern), "rule")

    def select_files(self, pattern: Union[str, Sequence[str]]) -> List[IFile]:
        return self._select(_parse_args_pattern(pattern), "file")

    def select_groups(self, pattern: Union[str, Sequence[str]]) -> List[IGroup]:
        """Obtain child groups or rules of this group.

        Signatures:

            1. `select(group_tree_pattern: str)`
            2. `select(group_tree_pattern: Sequence[str], group:bool=False)`

        Args for Signature 1:
            group_tree_pattern (str):
                Pattern of the relative name of child nodes of this group.
                Pattern consists of names concatenated with the delimiter '/'.
                Double star '**' can appear as a name indicating zero or
                more repetition of arbitrary names.

                Single star can appear as a part of a name indicating zero
                or more repetition of arbitrary character.

                If `group_tree_pattern[-1] == '/'`, it matches groups only.
                Otherwise, it matches rules only.

                For example, calling g.select(pattern) with a pattern

                * `"a/b"  matches a rule `g.a.b`
                * "a/b/" matches a group `g.a.b`
                * "a*"   matches rules `g.a`, `g.a1`, `g.a2`, etc
                * "a*/"  matches groups `g.a`, `g.a1`, `g.a2`, etc
                * `"**"`   matches all the offspring rules of `g`
                * `"**/"`  matches all the offspring groups of `g`
                * `"a/**"` matches all the offspring rules of the group `g.a`
                * `"**/b"` matches all the offspring rules of `g` of name "b"

            group: ignored

        Args for Signature-2:
            group_tree_pattern (list[str] | tuple[str]):
                Pattern representation using a sequence of names.

                Following two are equivalent:

                * `g.select(["a", "*", "c", "**"])`
                * `g.select("a/*/c/**")`

                Following two are equivalent:

                * `g.select(["a", "*", "c", "**"], True)`
                * `g.select("a/*/c/**/")`

            group (bool):
                if False (default), select rules only.
                if True, select groups only.

        Returns:
            list[RuleNodeLike]|list[Group]: rule nodes or group nodes.

            * called with Signature-1 and pattern[-1] != '/' or
            * called with Signature-2 and group is False

        Note:
            Cases where Signature-2 is absolutely necessary is when you need
            to select a node whose name contains "/".
            For example, ::

                g = create_group('group')

                # this rule's name is "dir/a.txt"
                rule = g.add('dir/a.txt', func)

                g.select(['dir/a.txt']) == [rule]  # OK
                g.select('dir/a.txt') != []  # trying to match g['dir']['a.txt']
        """
        return self._select(_parse_args_pattern(pattern), "group")


def _parse_args_pattern(pattern: object) -> List[str]:
    if isinstance(pattern, str):
        if len(pattern) == 0:
            raise ValueError("pattern must not be an empty str")

        pattern = pattern.strip("/")
        return re.split("/+", pattern)
    elif isinstance(pattern, Sequence):
        if not all(
            isinstance(v, str)
            for v in pattern  # pyright: ignore [reportUnknownVariableType]
        ):
            raise TypeError("Pattern sequence items must be str")

        return list(pattern)  # pyright: ignore [reportUnknownVariableType]
    else:
        raise TypeError("Pattern must be str or sequence of str")
