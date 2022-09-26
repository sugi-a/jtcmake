import sys, os, hashlib, json, pickle, hashlib, hmac
from pathlib import Path, PurePath
from collections import namedtuple

from ..core.abc import IRule
from ..core import check_update_result
from .file import File, VFile


class Rule(IRule):
    def __init__(
        self,
        yfiles,
        xfiles,
        xfile_is_orig,
        deplist,
        method,
        args,
        kwargs,
        memo,
        name=None,
    ):
        assert len(xfiles) == len(xfile_is_orig)

        self.yfiles = yfiles
        self.xfiles = xfiles
        self.xfile_is_orig = xfile_is_orig
        self._deplist = deplist
        self._method = method
        self._args = args
        self._kwargs = kwargs
        self.name = name
        self.memo = memo

    def check_update(self, par_updated, dry_run):
        for f, is_orig in zip(self.xfiles, self.xfile_is_orig):
            if not f.exists():
                if not dry_run or is_orig:
                    return check_update_result.Infeasible(
                        f"Input file {f} is missing"
                    )
            elif os.path.getmtime(f) == 0:
                if not dry_run or is_orig:
                    return check_update_result.Infeasible(
                        f"Input file {f} has mtime of 0. Input files"
                        " with mtime of 0 are considered to be invalid."
                    )

        if any(not f.exists() for f in self.yfiles):
            return check_update_result.Necessary()

        oldest_y = min(os.path.getmtime(f) for f in self.yfiles)

        if oldest_y <= 0:
            return check_update_result.Necessary()

        if dry_run and par_updated:
            return check_update_result.PossiblyNecessary()

        for f in self.xfiles:
            if isinstance(f, File) and os.path.getmtime(f) > oldest_y:
                return check_update_result.Necessary()

        if not self.memo.compare_to_saved(self.metadata_fname):
            return check_update_result.Necessary()

        return check_update_result.UpToDate()

    def preprocess(self, callback):
        for f in self.yfiles:
            try:
                os.makedirs(f.parent, exist_ok=True)
            except:
                pass

    def postprocess(self, callback, succ):
        if succ:
            self.update_memo()
        else:
            # set mtime to 0
            for f in self.yfiles:
                try:
                    os.utime(f, (0, 0))
                except:
                    pass

            # delete vfile cache
            try:
                os.remove(self.metadata_fname)
            except:
                pass

    @property
    def metadata_fname(self):
        p = PurePath(self.yfiles[0])
        return p.parent / ".jtcmake" / p.name

    def update_memo(self):
        self.memo.save_memo(self.metadata_fname)

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
    def deplist(self):
        return self._deplist
