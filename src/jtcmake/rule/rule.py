import sys, os, hashlib, json, pickle, hashlib, hmac
from pathlib import Path, PurePath
from collections import namedtuple

from ..core.abc import IRule
from .file import IFile, IVFile


class Rule(IRule):
    def __init__(
        self,
        yfiles,
        xfiles,
        deplist,
        method,
        args,
        kwargs,
        memo,
        name=None,
    ):
        self.yfiles = yfiles
        self.xfiles = xfiles
        self._deplist = deplist
        self._method = method
        self._args = args
        self._kwargs = kwargs
        self.name = name
        self.memo = memo

    def should_update(self, par_updated, dry_run):
        if dry_run and par_updated:
            return True

        for f in self.xfiles:
            if not os.path.exists(f.path):
                raise Exception(f"Input file {f.path} is missing")

            if os.path.getmtime(f.path) == 0:
                raise Exception(
                    f"Input file {f.path} has mtime of 0. Input files"
                    " with mtime of 0 are considered to be invalid."
                )

        if any(not os.path.exists(f.path) for f in self.yfiles):
            return True

        oldest_y = min(os.path.getmtime(f.path) for f in self.yfiles)

        if oldest_y <= 0:
            return True

        for f in self.xfiles:
            if isinstance(f, IFile) and os.path.getmtime(f.path) > oldest_y:
                return True

        if not self.memo.compare_to_saved(self.metadata_fname):
            return True

        return False

    def preprocess(self, callback):
        for f in self.yfiles:
            try:
                os.makedirs(f.path.parent, exist_ok=True)
            except:
                pass

    def postprocess(self, callback, succ):
        if succ:
            self.update_memo()
        else:
            # set mtime to 0
            for f in self.yfiles:
                try:
                    os.utime(f.path, (0, 0))
                except:
                    pass

            # delete vfile cache
            try:
                os.remove(self.metadata_fname)
            except:
                pass

    @property
    def metadata_fname(self):
        p = PurePath(self.yfiles[0].path)
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

