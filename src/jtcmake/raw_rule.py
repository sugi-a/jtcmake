from __future__ import annotations
from abc import ABCMeta, abstractmethod
import os
from pathlib import Path
from typing import (
    Callable,
    Generic,
    Iterable,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Dict,
    Collection,
)

from .core.abc import IRule, UpdateResults, TUpdateResult, Callback


class IMemo(metaclass=ABCMeta):
    @abstractmethod
    def compare(self, other: IMemo) -> bool:
        ...

    @abstractmethod
    def dumps(self) -> Iterable[bytes]:
        ...

    @classmethod
    @abstractmethod
    def loads(cls, data: bytes) -> IMemo:
        ...


TId = TypeVar("TId")


class Rule(IRule, Generic[TId]):
    __slots__ = [
        "yfiles",
        "xfiles",
        "xfile_is_orig",
        "xfile_is_vf",
        "_deplist",
        "_method",
        "_args",
        "_kwargs",
        "_id",
        "memo",
    ]

    def __init__(
        self,
        yfiles: Sequence[Path],
        xfiles: Sequence[Path],
        xfile_is_orig: Sequence[bool],
        xfile_is_vf: Sequence[bool],
        deplist: Set[int],
        method: Callable[..., object],
        args: Tuple[object, ...],
        kwargs: Dict[str, object],
        memo: IMemo,
        id: TId,
    ):
        assert len(xfiles) == len(xfile_is_orig)

        self.yfiles = yfiles
        self.xfiles = xfiles
        self.xfile_is_orig = xfile_is_orig
        self.xfile_is_vf = xfile_is_vf
        self._deplist = deplist
        self._method = method
        self._args = args
        self._kwargs = kwargs
        self._id = id
        self.memo = memo

    def check_update(self, par_updated: bool, dry_run: bool) -> TUpdateResult:
        """
        Prerequisite: the y-list has at least one item.

        Procedure:

        - dry run:
            1. dry_run?
                yes: Any original x does not exist or has mtime of 0: Infeasible
                no:  Any x does not exist or has mtime of 0: Infeasible
            2. Any y is missing or has a mtime of 0: Necessary
            3. dry_run and any parent was updated: PossiblyNecessary
            4. Any x of type File is newer than the oldest y: Necessary
            5. Memoized values are updated: Necessary
            6. Otherwise: UpToDate
        """
        funcs = [
            _check_update_1,
            _check_update_2,
            _check_update_3,
            _check_update_4,
            _check_update_5,
        ]

        for func in funcs:
            res = func(
                ys=self.yfiles,
                xs=self.xfiles,
                xisorig=self.xfile_is_orig,
                xisvf=self.xfile_is_vf,
                dry_run=dry_run,
                par_updated=par_updated,
                memo=self.memo,
                old_memo_file=self.metadata_fname,
            )
            if res is not None:
                return res

        return UpdateResults.UpToDate()

    def preprocess(self, callback: Callback):
        del callback
        for f in self.yfiles:
            try:
                os.makedirs(f.parent, exist_ok=True)
            except Exception:
                pass

    def postprocess(self, callback: Callback, succ: bool):
        del callback
        if succ:
            self.update_memo()
        else:
            # set mtime to 0
            for f in self.yfiles:
                try:
                    os.utime(f, (0, 0))
                except Exception:
                    pass

            # delete vfile cache
            try:
                os.remove(self.metadata_fname)
            except Exception:
                pass

    @property
    def metadata_fname(self) -> Path:
        p = self.yfiles[0]
        return p.parent / ".jtcmake" / p.name

    def update_memo(self):
        os.makedirs(os.path.dirname(self.metadata_fname), exist_ok=True)
        with self.metadata_fname.open("wb") as f:
            f.writelines(self.memo.dumps())

    @property
    def method(self):
        return self._method

    @property
    def args(self):
        return self._args

    @property
    def kwargs(self):
        return self._kwargs

    @property
    def deps(self):
        return self._deplist

    @property
    def id(self) -> TId:
        return self._id


def _check_update_1(
    xs: Sequence[Path],
    xisorig: Sequence[bool],
    dry_run: bool,
    **_: object,
) -> Optional[TUpdateResult]:
    for f, isorig in zip(xs, xisorig):
        if not f.exists():
            if not dry_run or isorig:
                return UpdateResults.Infeasible(f"Input file {f} is missing")
        elif os.path.getmtime(f) == 0:
            if not dry_run or isorig:
                return UpdateResults.Infeasible(
                    f"Input file {f} has mtime of 0. Input files"
                    " with mtime of 0 are considered to be invalid."
                )

    return None


def _check_update_2(
    ys: Collection[Path], **_: object
) -> Optional[TUpdateResult]:
    if any(not f.exists() for f in ys):
        return UpdateResults.Necessary()

    if any(os.path.getmtime(f) == 0 for f in ys):
        return UpdateResults.Necessary()


def _check_update_3(
    dry_run: bool, par_updated: bool, **_: object
) -> Optional[TUpdateResult]:
    if dry_run and par_updated:
        return UpdateResults.PossiblyNecessary()


def _check_update_4(
    ys: Collection[Path], xs: Sequence[Path], xisvf: Sequence[bool], **_: object
) -> Optional[TUpdateResult]:
    assert all(y.exists() for y in ys)
    getmtime = os.path.getmtime
    oldest_y = min(os.path.getmtime(f) for f in ys)
    if any(not isvf and getmtime(x) > oldest_y for x, isvf in zip(xs, xisvf)):
        return UpdateResults.Necessary()


def _check_update_5(
    memo: IMemo, old_memo_file: Path, **_: object
) -> Optional[TUpdateResult]:
    if not os.path.exists(old_memo_file):
        return UpdateResults.Necessary()

    with old_memo_file.open("rb") as f:
        old_memo = memo.loads(f.read())

    if not memo.compare(old_memo):
        return UpdateResults.Necessary()
