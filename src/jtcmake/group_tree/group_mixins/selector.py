from __future__ import annotations

import re
from abc import ABCMeta
from typing import Any, List, Literal, Optional, Sequence, Tuple, TypeVar, Union

from ..core import IFile, IGroup, IRule

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

    def select_rules(
        self, pattern: Union[str, List[str], Tuple[str]]
    ) -> List[IRule]:
        """
        Create list of rules in this group sub-tree that match ``pattern``.

        This is the rule-version of :func:`select_groups`.
        See its documentation for detail.

        Examples:

            .. code-block:: text

               <ROOT>
               |-- a0(r)
               |-- a1
               |   `-- a2(r)
               `-- a3
                   `-- a4(r)

            .. testcode::

               from jtcmake import UntypedGroup, SELF

               # Building the above group tree
               g = UntypedGroup()  # Root group
               g.add("a0", lambda x: ())(SELF)
               g.add_group("a1")
               g.a1.add("a2", lambda x: ())(SELF)
               g.add_group("a3")
               g.a3.add("a4", lambda x: ())(SELF)

               assert g.select_rules("a*") == [g.a0]
               assert g.select_rules("*/a*") == [g.a1.a2, g.a3.a4]
        """
        return self._select(_parse_args_pattern(pattern), "rule")

    def select_files(
        self, pattern: Union[str, List[str], Tuple[str]]
    ) -> List[IFile]:
        """
        Create list of files in this group sub-tree that match ``pattern``.

        This is the file-version of :func:`select_groups`.
        See its documentation for detail.

        Examples:

            .. code-block:: text

               <ROOT>
               |-- a(r)
               |   |-- a (f:a.txt)
               |   `-- b (f:b.html)
               |
               `-- b(g)
                   `-- a(r)
                       `-- a (f:a.txt)

            .. testcode::

               from jtcmake import UntypedGroup, SELF

               # Building the above group tree
               g = UntypedGroup()  # Root group
               g.add("a", { "a": "a.txt", "b": "b.html" }, lambda x,y: ())(SELF.a, SELF.b)
               g.add_group("b")
               g.b.add("a", { "a": "a.txt" }, lambda x: ())(SELF.a)

               assert g.select_files("**/a") == [g.a.a, g.b.a.a]
               assert g.select_files("a/*") == [g.a.a, g.a.b]
        """
        return self._select(_parse_args_pattern(pattern), "file")

    def select_groups(
        self, pattern: Union[str, List[str], Tuple[str]]
    ) -> List[IGroup]:
        """
        Create list of groups in this group sub-tree that match ``pattern``.
        The list may include this group itself.

        Groups are gathered based on the given pattern in a manner similar to
        how we specify a set of files using a glob pattern on Unix.

        Args:
            pattern:
                str or list/tuple of str representing a pattern of
                relative names of offspring nodes.

                If ``pattern`` is a list/tuple of strs,
                it must be a sequence of *base name patterns* like
                ``["a", "b", "c"]`` or ``["a", "*b*", "c", "**"]``.

                If ``pattern`` is a str, it will be internally translated into
                an equivalent list-of-str pattern by splitting it with ``/``.
                So, for example, ``g.select_groups("a/b/c") is equivalent to
                ``g.select_groups(["a", "b", "c"])``.

        Suppose we have the following group tree (the tree may have rules as
        well but we omit them since this method collects groups only).

        .. code-block:: text

           <ROOT>
           |
           |-- a1
           |   |-- b1
           |   `-- b2
           |       `-- c1
           |
           |-- a2
           |   `-- b1
           |
           `-- a1/b1

        We use a list of strs to identify each group node.
        For example, the (absolute) name of the forth group from the top
        (the deepest one) is ``["a1", "b2", "c1"]``.
        Its *relative name* with respect to the group ``["a1"]`` is
        ``["b2", "c1"]``, and ``"c1"`` is its *base name*.

        Pattern matching is basically as simple as *pattern* ``["a1", "b1"]``
        matches the *relative name* ``["a1", "b1"]``.
        Additionally, you can use wildcard ``*`` in patterns as follows.

        * Double stars ``**`` can appear as a special base name indicating
          zero or more repetition of arbitrary base names.
          It may NOT appear inside a base name like ``a/**b/c``
        * Single stars ``*`` can appear inside a base name indicating zero
          or more repetition of arbitrary character.

        Examples:

            .. testcode::

                from jtcmake import UntypedGroup

                # Building the above group tree
                g = UntypedGroup()  # Root group
                g.add_group("a1")
                g.a1.add_group("b1")
                g.a1.add_group("b2")
                g.a1.b2.add_group("c1")
                g.add_group("a2")
                g.a2.add_group("b1")
                g.add_group("a1/b1")

                assert g.select_groups("a1/b1") == [g.a1.b1]
                assert g.select_groups(["a1", "b1"]) == [g.a1.b1]

                # In the following example,  ``/`` in the base name is treated
                # as a normal character and has no effect as a base name boundary
                assert g.select_groups(["a1/b1"]) == [g["a1/b1"]]

                assert g.select_groups("a*") == [g.a1, g.a2, g["a1/b1"]]
                assert g.select_groups("*/*1") == [g.a1.b1, g.a2.b1]
                assert g.select_groups("**/*1") == [
                    g.a1, g.a1.b1, g.a1.b2.c1, g.a2.b1, g["a1/b1"]
                ]
                assert g.select_groups("**") == [
                    g,  # root is included
                    g.a1,
                    g.a1.b1,
                    g.a1.b2,
                    g.a1.b2.c1,
                    g.a2,
                    g.a2.b1,
                    g["a1/b1"],
                ]
                assert g.a1.select_groups("*") == g.select_groups("a1/*")

        Note:
            Current implementation collects nodes using pre-order DFS but
            it may be changed in the future.
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
