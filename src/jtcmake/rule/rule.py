import os
from pathlib import Path
from typing import Any, Callable, Generic, Sequence, Set, TypeVar

from ..rule.memo.abc import IMemo
from ..core.abc import IRule, UpdateResults, TUpdateResult, Callback
from .file import File, IFile

TId = TypeVar("TId")


class Rule(IRule, Generic[TId]):
    __slots__ = [
        "yfiles",
        "xfiles",
        "xfile_is_orig",
        "_deplist",
        "_method",
        "_args",
        "_kwargs",
        "_id",
        "memo",
    ]

    def __init__(
        self,
        yfiles: Sequence[IFile],
        xfiles: Sequence[IFile],
        xfile_is_orig: Sequence[bool],
        deplist: Set[int],
        method: Callable[..., object],
        args: Any,
        kwargs: Any,
        memo: IMemo,
        id: TId,
    ):
        assert len(xfiles) == len(xfile_is_orig)

        self.yfiles = yfiles
        self.xfiles = xfiles
        self.xfile_is_orig = xfile_is_orig
        self._deplist = deplist
        self._method = method
        self._args = args
        self._kwargs = kwargs
        self._id = id
        self.memo = memo

    def check_update(self, par_updated: bool, dry_run: bool) -> TUpdateResult:
        for f, is_orig in zip(self.xfiles, self.xfile_is_orig):
            if not f.exists():
                if not dry_run or is_orig:
                    return UpdateResults.Infeasible(
                        f"Input file {f} is missing"
                    )
            elif os.path.getmtime(f) == 0:
                if not dry_run or is_orig:
                    return UpdateResults.Infeasible(
                        f"Input file {f} has mtime of 0. Input files"
                        " with mtime of 0 are considered to be invalid."
                    )

        if any(not f.exists() for f in self.yfiles):
            return UpdateResults.Necessary()

        oldest_y = min(os.path.getmtime(f) for f in self.yfiles)

        if oldest_y <= 0:
            return UpdateResults.Necessary()

        if dry_run and par_updated:
            return UpdateResults.PossiblyNecessary()

        for f in self.xfiles:
            if isinstance(f, File) and os.path.getmtime(f) > oldest_y:
                return UpdateResults.Necessary()

        memo = self.memo.memo
        if not memo.compare(memo.load(self.metadata_fname)):
            return UpdateResults.Necessary()

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
        p = Path(self.yfiles[0])
        return p.parent / ".jtcmake" / p.name

    def update_memo(self):
        os.makedirs(os.path.dirname(self.metadata_fname), exist_ok=True)
        self.memo.memo.save(self.metadata_fname)

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
