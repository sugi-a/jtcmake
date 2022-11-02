import os, sys, time
from abc import ABCMeta, abstractmethod
from pathlib import Path
from logging import Logger
from typing import (
    Callable,
    Optional,
    Tuple,
    TypeVar,
    Union,
    Literal,
    Sequence,
    List,
)
from typing_extensions import TypeAlias

from ...core.make import MakeSummary

from .selector import get_offspring_groups

from ...rule.memo.abc import IMemo
from ...rule.memo.pickle_memo import PickleMemo
from ...rule.memo.str_hash_memo import StrHashMemo
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

StrOrPath: TypeAlias = "Union[str, os.PathLike[str]]"

MemoKind = Literal["str_hash", "pickle"]

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
        memo_kind: MemoKind = "str_hash",
        pickle_key: Union[None, str, bytes] = None,
    ):
        writer = basic_init_create_logwriter(
            loglevel, use_default_logger, logfile
        )

        memo_factory = parse_args_create_memo_factory(memo_kind, pickle_key)

        info = GroupTreeInfo(writer, memo_factory)

        self.__init_as_child__(info, self, ())

        self.set_prefix(parse_args_prefix(dirname, prefix))

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

    if logfile is None:
        logfile_: Sequence[object] = []
    else:
        logfile_: Sequence[object] = (
            logfile if isinstance(logfile, Sequence) else [logfile]
        )

    writers: List[IWriter] = [create_logwriter(f, loglevel) for f in logfile_]

    if use_default_logger:
        writers.append(create_default_logwriter(loglevel))

    return WritersWrapper(writers)


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


def parse_args_create_memo_factory(
    kind: object, pickle_key: object
) -> Callable[[object], IMemo]:
    if kind == "str_hash":
        if pickle_key is not None:
            raise TypeError(
                "pickle_key must not be specified for " "str_hash memoization"
            )
        return StrHashMemo
    elif kind == "pickle":
        if pickle_key is None:
            raise TypeError("pickle_key must be specified")

        if isinstance(pickle_key, str):
            try:
                pickle_key_ = bytes.fromhex(pickle_key)
            except ValueError as e:
                raise ValueError(
                    "If given as str, pickle_key must be a hexadecimal string"
                ) from e
        elif isinstance(pickle_key, bytes):
            pickle_key_ = pickle_key
        else:
            raise TypeError("pickle_key must be bytes or hexadecimal str")

        def _memo_factory_pickle(args: object) -> IMemo:
            return PickleMemo(args, pickle_key_)

        return _memo_factory_pickle
    else:
        raise TypeError('memo kind must be "str_hash" or "pickle"')

