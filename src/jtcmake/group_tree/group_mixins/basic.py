from __future__ import annotations

import hashlib
import os
import sys
import time
from abc import ABCMeta, abstractmethod
from logging import Logger
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, TypeVar, Union

from ...core.make import MakeSummary
from ...logwriter import (
    ColorTextWriter,
    HTMLFileWriterOpenOnDemand,
    HTMLJupyterWriter,
    IWriter,
    LoggerWriter,
    Loglevel,
    TextFileWriterOpenOnDemand,
    TextWriter,
    WritableProtocol,
    WritersWrapper,
    term_is_jupyter,
    typeguard_loglevel,
)
from ...memo import (
    IMemo,
    Memo,
    string_deserializer,
    string_normalizer,
    string_serializer,
)
from ...utils.strpath import StrOrPath
from ..atom import unwrap_memo_values
from ..core import GroupTreeInfo, IGroup, make, parse_args_prefix
from .selector import get_offspring_groups

T = TypeVar("T")


class BasicInitMixin(IGroup, metaclass=ABCMeta):
    def __init__(
        self,
        dirname: Optional[StrOrPath] = None,
        prefix: Optional[StrOrPath] = None,
        *,
        loglevel: Optional[Loglevel] = None,
        use_default_logger: bool = True,
        logfile: Union[
            None,
            StrOrPath,
            Logger,
            WritableProtocol,
            Sequence[Union[StrOrPath, Logger, WritableProtocol]],
        ] = None,
        memodir: StrOrPath | None = None,
    ):
        """
        Args:
            driname: directory name of this group.
                ``dirname="foo"`` is equivalent to ``prefix="foo/"``
            prefix: path prefix of this group.
                You may not specify ``dirname`` and ``prefix`` at the same time.
                If both ``dirname`` and ``prefix`` is none, prefix will be ""
            use_default_logger: if True, logs will be printed to stderr or
                displayed as HTML if the code is running on Jupyter Notebook.
            logfile: str, PathLike, Logger, object with a ``write(str)`` method,
                or list/tuple of them, indicating the target(s) to which logs
                should be output.
        """
        writer = basic_init_create_logwriter(
            loglevel, use_default_logger, logfile
        )

        if memodir is None:
            memo_factory = string_memo_factory
        else:
            if not os.path.exists(memodir):
                raise FileNotFoundError(f"memodir ({memodir}) was not found")

            memo_factory = CustomDirMemoFactory(Path(memodir))

        info = GroupTreeInfo(writer, memo_factory, self)

        self.__init_as_child__(info, self, ())

        self.set_prefix(prefix=parse_args_prefix(dirname, prefix))

    @abstractmethod
    def __init_as_child__(
        self,
        info: GroupTreeInfo,
        parent: IGroup,
        name: Tuple[str, ...],
    ):
        ...


class BasicMixin(IGroup, metaclass=ABCMeta):
    def clean(self) -> None:
        """
        Delete all the existing files of this group.
        """
        for g in get_offspring_groups(self):
            for r in g.rules.values():
                r.clean()

    def touch(
        self,
        file: bool = True,
        memo: bool = True,
        create: bool = True,
        t: Optional[float] = None,
    ) -> None:
        """
        For every rule in the group, touch (set mtime to now) the output files
        and force the memo to record the current input state.

        Args:
            file (bool): if False, files won't be touched. Defaults to True.
            memo (bool): if False, memos won't be modified. Defaults to True.
            create (bool): if True, missing files will be created. Otherwise,
                only the existing files will be touched.
                This option has no effect with ``file=False``.
        """
        if t is None:
            t = time.time()

        for g in get_offspring_groups(self):
            for r in g.rules.values():
                r.touch(file, memo, create, t)

    def make(
        self,
        dry_run: bool = False,
        keep_going: bool = False,
        *,
        njobs: Optional[int] = None,
    ) -> MakeSummary:
        """Make rules in this group and their dependencies

        Args:
            dry_run (bool):
                instead of actually excuting the methods,
                print expected execution logs.
            keep_going (bool):
                If False (default), stop everything when a rule fails.
                If True, when a rule fails, keep executing other rules
                except the ones depend on the failed rule.
            njobs (int):
                Maximum number of rules that can be made simultaneously using
                multiple threads and processes.
                Defaults to 1 (single process, single thread).

        See also:
            See the description of jtcmake.make for more detail of njobs
        """
        return make(
            self,
            dry_run=dry_run,
            keep_going=keep_going,
            njobs=njobs,
        )


def basic_init_create_logwriter(
    loglevel: object, use_default_logger: object, logfile: object
) -> IWriter:
    loglevel = loglevel or "info"

    if not typeguard_loglevel(loglevel):
        raise TypeError(f"loglevel must be {Loglevel}. Given {loglevel}")

    if not (isinstance(use_default_logger, bool) or use_default_logger is None):
        raise TypeError(
            f"use_default_logger must be bool or None. "
            f"Given {use_default_logger}"
        )

    writers = create_logwriter_list(loglevel, logfile)

    if use_default_logger:
        writers.append(create_default_logwriter(loglevel))

    return WritersWrapper(writers)


def create_logwriter_list(loglevel: Loglevel, logfile: object) -> List[IWriter]:
    if logfile is None:
        return []
    elif isinstance(logfile, (list, tuple)):
        return [
            create_logwriter(f, loglevel)
            for f in logfile  # pyright: ignore [reportUnknownVariableType]
        ]
    else:
        return [create_logwriter(logfile, loglevel)]


def create_logwriter(f: object, loglevel: Loglevel) -> IWriter:
    """
    Args:
        f (str|PathLike|Logger|WritableProtocol): logging destination
    """
    if isinstance(f, (str, os.PathLike)):
        if Path(f).suffix == ".html":
            return HTMLFileWriterOpenOnDemand(loglevel, f)
        else:
            return TextFileWriterOpenOnDemand(loglevel, f)

    if isinstance(f, Logger):
        return LoggerWriter(f)

    if isinstance(f, WritableProtocol):
        _isatty = getattr(f, "isatty", None)
        if callable(_isatty) and _isatty():
            return ColorTextWriter(f, loglevel)

        return TextWriter(f, loglevel)

    raise TypeError(
        "Logging target must be either str (file name), os.PathLike, "
        "logging.Logger, or and object with `write` method. "
        f"Given {f}"
    )


def create_default_logwriter(loglevel: Loglevel) -> IWriter:
    if term_is_jupyter():
        return HTMLJupyterWriter(loglevel, os.getcwd())
    elif sys.stderr.isatty():
        return ColorTextWriter(sys.stderr, loglevel)
    else:
        return TextWriter(sys.stderr, loglevel)


def string_memo_factory(output0: Path, args: object) -> IMemo:
    args, lazy_args = unwrap_memo_values(args)
    memo_file = _get_default_memo_file(output0)
    return Memo(
        args,
        lazy_args,
        memo_file,
        string_normalizer,
        string_serializer,
        string_deserializer,
    )


def _get_default_memo_file(output0: Path) -> Path:
    return output0.parent / ".jtcmake" / (output0.name + ".json")


class CustomDirMemoFactory:
    __slots__ = ["memodir"]
    memodir: Path

    def __call__(self, output0: Path, args: object) -> IMemo:
        args, lazy_args = unwrap_memo_values(args)
        memo_file = self.memodir / _create_memo_file_basename(output0)
        return Memo(
            args,
            lazy_args,
            memo_file,
            string_normalizer,
            string_serializer,
            string_deserializer,
            extra_info=os.path.abspath(output0),
        )

    def __init__(self, memodir: Path) -> None:
        self.memodir = memodir


def _create_memo_file_basename(output0: Path) -> str:
    stem = hashlib.md5(os.path.abspath(output0).encode("utf8")).digest().hex()
    return stem + ".json"
