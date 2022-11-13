import os
import sys
import time
from abc import ABCMeta, abstractmethod
from pathlib import Path
from logging import Logger
from typing import (
    Callable,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    Sequence,
    List,
)

from ..atom import unwrap_memo_values

from ...memo import ILazyMemo, create_lazy_memo_type, StrHashMemo, IMemo

from ...core.make import MakeSummary

from .selector import get_offspring_groups

from ...logwriter import (
    Loglevel,
    WritableProtocol,
    HTMLJupyterWriter,
    IWriter,
    WritersWrapper,
    HTMLFileWriterOpenOnDemand,
    TextFileWriterOpenOnDemand,
    LoggerWriter,
    ColorTextWriter,
    TextWriter,
    typeguard_loglevel,
    term_is_jupyter,
)
from ..core import IGroup, GroupTreeInfo, make, parse_args_prefix
from ...utils.strpath import StrOrPath


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
    ):
        writer = basic_init_create_logwriter(
            loglevel, use_default_logger, logfile
        )

        lazy_memo_type = create_lazy_memo_type(StrHashMemo.create)
        memo_factory = create_lazy_memo_factory(lazy_memo_type)

        info = GroupTreeInfo(writer, memo_factory)

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
                Maximum number of rules that can be made concurrently.
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
        logfile_: Sequence[object] = logfile
        return [create_logwriter(f, loglevel) for f in logfile_]
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


def create_lazy_memo_factory(
    lazy_memo_type: Type[ILazyMemo],
) -> Callable[[object], IMemo]:
    def _res(args: object) -> IMemo:
        args, lazy_args = unwrap_memo_values(args)
        return lazy_memo_type.create(args, lazy_args)

    return _res
