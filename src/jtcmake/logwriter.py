import abc
import html
import os
from logging import Logger
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from typing_extensions import Literal, Protocol, TypeGuard, runtime_checkable

from .utils.strpath import StrOrPath

T = TypeVar("T")


def _first_non_none(*t: T) -> T:
    assert len(t) > 0
    for x in t:
        if x is not None:
            return x

    return t[-1]


class RichStrAttr(NamedTuple):
    c: Optional[Tuple[int, int, int]] = None
    bg: Optional[Tuple[int, int, int]] = None
    link: Optional[StrOrPath] = None


class RichStr(str):
    attr: RichStrAttr

    def __new__(cls, s: str, *_args: object, **_kwargs: object):
        return super().__new__(cls, s)

    def __init__(
        self,
        s: str,
        c: Optional[Tuple[int, int, int]] = None,
        bg: Optional[Tuple[int, int, int]] = None,
        link: Optional[StrOrPath] = None,
        default: Optional[RichStrAttr] = None,
    ):
        a = s.attr if isinstance(s, RichStr) else RichStrAttr()
        b = default or RichStrAttr()

        self.attr = RichStrAttr(
            _first_non_none(c, a.c, b.c),
            _first_non_none(bg, a.bg, b.bg),
            _first_non_none(link, a.link, b.link),
        )

    def __add__(self, rhs: object):
        if type(rhs) == str:
            return RichStr(str(self) + str(rhs), *self.attr)
        else:
            return NotImplemented

    def __radd__(self, lhs: object):
        if isinstance(lhs, str):
            return RichStr(str(lhs) + str(self), *self.attr)
        else:
            return NotImplemented


Loglevel = Literal["debug", "info", "warning", "error"]


def typeguard_loglevel(loglevel: object) -> TypeGuard[Loglevel]:
    return loglevel in {"debug", "info", "warning", "error"}


QUANT_LOG_LEVEL: Mapping[Loglevel, int] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}


class IWriter:
    loglevel: Loglevel

    def __init__(self, loglevel: Loglevel):
        assert loglevel in {"debug", "info", "warning", "error"}

        self.loglevel = loglevel

    @abc.abstractmethod
    def _write(self, *args: str, level: Loglevel):
        ...

    def write(self, *args: str, level: Loglevel):
        if QUANT_LOG_LEVEL[self.loglevel] <= QUANT_LOG_LEVEL[level]:
            self._write(*args, level=level)

    def debug(self, *args: str):
        self.write(*args, level="debug")

    def info(self, *args: str):
        self.write(*args, level="info")

    def warning(self, *args: str):
        self.write(*args, level="warning")

    def error(self, *args: str):
        self.write(*args, level="error")


class WritersWrapper(IWriter):
    def __init__(
        self, writers: Sequence[IWriter], loglevel: Optional[Loglevel] = None
    ):
        super().__init__(loglevel or "debug")
        assert all(isinstance(w, IWriter) for w in writers)
        self.writers = writers

    def _write(self, *args: str, level: Loglevel):
        for writer in self.writers:
            writer.write(*args, level=level)


@runtime_checkable
class WritableProtocol(Protocol):
    def write(self, __t: str) -> Any:
        ...


class TextWriter(IWriter):
    def __init__(self, writable: WritableProtocol, loglevel: Loglevel):
        super().__init__(loglevel)
        self.writable = writable

    def _write(self, *args: str, level: Loglevel):
        self.writable.write("".join(map(str, args)) + "\n")


class ColorTextWriter(IWriter):
    def __init__(self, writable: WritableProtocol, loglevel: Loglevel):
        super().__init__(loglevel)
        self.writable = writable

    def _write(self, *args: str, level: Loglevel):
        color = (
            {
                "debug": None,
                "info": None,
                "warning": (0x9F, 0x60, 0x00),
                "error": (0xD8, 0x00, 0x0C),
            }
        ).get(level)

        bgcolor = (
            {
                "debug": None,
                "info": None,
                "warning": None,
                "error": None,
            }
        ).get(level)

        args_ = [RichStr(x, default=RichStrAttr(color, bgcolor)) for x in args]
        self.writable.write(create_color_str(args_) + "\n")


class LoggerWriter(IWriter):
    def __init__(self, logger: Logger):
        super().__init__("debug")
        self.logger = logger

    def _write(self, *args: str, level: Loglevel):
        msg = "".join(map(str, args))

        if level == "debug":
            self.logger.debug(msg)
        elif level == "info":
            self.logger.info(msg)
        elif level == "warning":
            self.logger.warning(msg)
        elif level == "error":
            self.logger.error(msg)


class TextFileWriterOpenOnDemand(IWriter):
    def __init__(self, loglevel: Loglevel, fname: StrOrPath):
        super().__init__(loglevel)

        os.makedirs(Path(fname).parent, exist_ok=True)

        self.fname = fname

    def _write(self, *args: str, level: Loglevel):
        with open(self.fname, "a") as f:
            f.write("".join(map(str, args)) + "\n")


HTML_BG_COLOR_MAP: Dict[Loglevel, Tuple[int, int, int]] = {
    "debug": (0xDF, 0xF2, 0xBF),
    "info": (0xFF, 0xFF, 0xFF),
    "warning": (0xFE, 0xEF, 0xB3),
    "error": (0xFF, 0xD2, 0xD2),
}
HTML_COLOR_MAP: Dict[Loglevel, Tuple[int, int, int]] = {
    "debug": (0x4F, 0x8A, 0x10),
    "info": (0, 0, 0),
    "warning": (0x9F, 0x60, 0x00),
    "error": (0xD8, 0x00, 0x0C),
}


class HTMLFileWriterOpenOnDemand(IWriter):
    fname: Path

    def __init__(
        self,
        loglevel: Loglevel,
        fname: StrOrPath,
    ):
        super().__init__(loglevel)

        os.makedirs(Path(fname).parent, exist_ok=True)

        self.fname = Path(os.path.abspath(fname))

    def _write(self, *args: str, level: Loglevel):
        color = HTML_COLOR_MAP[level]
        bgcolor = HTML_BG_COLOR_MAP[level]

        args_ = [RichStr(x, default=RichStrAttr(color, bgcolor)) for x in args]

        with open(self.fname, "a") as f:
            f.write(
                '<html><head><meta charset="utf-8"><title>log</title></head>'
                '<body><pre style="background-color: '
                f'rgb({bgcolor[0]}, {bgcolor[1]}, {bgcolor[2]})">'
            )
            f.write(create_html(args_, self.fname.parent))
            f.write("</pre></body></html>")


class HTMLJupyterWriter(IWriter):
    basedir: Path

    def __init__(self, loglevel: Loglevel, basedir: Optional[StrOrPath] = None):
        super().__init__(loglevel)
        from IPython.display import HTML, display  # pyright: ignore

        del display, HTML

        self.basedir = Path(basedir if basedir else os.getcwd())

    def _write(self, *args: str, level: Loglevel):
        from IPython.display import HTML, display  # pyright: ignore

        color = HTML_COLOR_MAP[level]
        bgcolor = HTML_BG_COLOR_MAP[level]

        args_ = [RichStr(x, default=RichStrAttr(color, bgcolor)) for x in args]

        display(
            HTML(
                '<pre style="background-color: '
                f'rgb({bgcolor[0]}, {bgcolor[1]}, {bgcolor[2]})">'
                f"{create_html(args_, self.basedir)}</pre>"
            )
        )


def create_html(sl: Sequence[str], basedir: StrOrPath) -> str:
    sl = [x if isinstance(x, RichStr) else RichStr(x) for x in sl]
    groups: List[List[RichStr]] = []
    for s in sl:
        if len(groups) >= 1 and s.attr == groups[-1][0].attr:
            groups[-1].append(s)
        else:
            groups.append([s])

    outs: List[str] = []
    for group in groups:
        s = RichStr("".join(group), *group[0].attr)
        outs.append(_richstr_to_html(s, str(basedir)))

    return "".join(outs)


def _richstr_to_html(s: RichStr, basedir: str) -> str:
    starts: List[str] = []
    ends: List[str] = []

    attr = s.attr

    if attr.link is not None:
        try:
            link = os.path.relpath(attr.link, basedir)
            print(link)
        except Exception:
            link = attr.link

        starts.append(f'<a href="{Path(link).as_posix()}">')
        ends.append("</a>")

    styles: List[str] = []
    if attr.c is not None:
        styles.append(f"color: rgb({attr.c[0]}, {attr.c[1]}, {attr.c[2]});")

    if attr.bg is not None:
        styles.append(
            f"background-color: rgb({attr.bg[0]}, {attr.bg[1]}, {attr.bg[2]});"
        )

    if len(styles) != 0:
        style = "".join(styles)
        starts.append(f'<span style="{style}">')
        ends.append("</span>")

    starts.append(html.escape(s))
    starts.extend(ends[::-1])
    return "".join(starts)


def create_color_str(sl: Sequence[str]) -> str:
    res: List[str] = []
    last_c = None
    last_bg = None
    for s in sl:
        if not isinstance(s, RichStr):
            last_bg = None
            last_c = None
            res.append("\x1b[49m\x1b[39m" + s)
            continue

        attr = s.attr

        if attr.bg != last_bg:
            last_bg = attr.bg
            if attr.bg is None:
                res.append("\x1b[49m")
            else:
                res.append(f"\x1b[48;5;{_comp_8bit_term_color(*attr.bg)}m")

        if attr.c != last_c:
            last_c = attr.c
            if attr.c is None:
                res.append("\x1b[39m")
            else:
                res.append(f"\x1b[38;5;{_comp_8bit_term_color(*attr.c)}m")

        res.append(str(s))

    res.append("\x1b[49m\x1b[39m")

    return "".join(res)


def _comp_8bit_term_color(r: int, g: int, b: int) -> int:
    r, g, b = (x * 6 // 256 for x in (r, g, b))
    return 16 + r * 36 + g * 6 + b


def term_is_jupyter() -> bool:
    try:
        from IPython.core.getipython import get_ipython  # pyright: ignore

        name = get_ipython().__class__.__name__  # pyright: ignore
        return name == "ZMQInteractiveShell"  # pyright: ignore
    except Exception:
        return False
