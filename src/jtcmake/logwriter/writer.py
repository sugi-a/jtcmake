import sys, html, abc, os
from logging import Logger
from pathlib import Path


def update_with_non_none(target, **kvs):
    for k, v in kvs.items():
        if v is not None:
            target[k] = v


class RichStr(str):
    def __new__(cls, s, *_args, **_kwargs):
        return super().__new__(cls, s)

    def __init__(self, s, *, c=None, bg=None, link=None, defaults=None):
        attr = {"c": None, "bg": None, "link": None}
        if defaults:
            update_with_non_none(attr, **defaults)
        if isinstance(s, RichStr):
            update_with_non_none(attr, **s.attr)
        update_with_non_none(attr, c=c, bg=bg, link=link)

        # TODO: use frozen dict
        self._attr = attr

    def __getattr__(self, k):
        return self._attr[k]

    def __add__(self, rhs):
        if isinstance(rhs, type(self)):
            return NotImplemented  # pass to __radd__
        elif isinstance(rhs, str):
            return RichStr(str(self) + str(rhs), **self._attr)
        else:
            return NotImplemented

    def __radd__(self, lhs):
        if isinstance(lhs, str):
            return RichStr(str(lhs) + str(self), **self._attr)
        else:
            return NotImplemented

    @property
    def attr(self):
        return self._attr


QUANT_LOG_LEVEL = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}


class IWriter:
    def __init__(self, loglevel):
        assert loglevel in {"debug", "info", "warning", "error"}

        self.loglevel = loglevel

    @abc.abstractmethod
    def _write(self, *args, level):
        ...

    def write(self, *args, level):
        if QUANT_LOG_LEVEL[self.loglevel] <= QUANT_LOG_LEVEL[level]:
            self._write(*args, level=level)

    def debug(self, *args):
        self.write(*args, level="debug")

    def info(self, *args):
        self.write(*args, level="info")

    def warning(self, *args):
        self.write(*args, level="warning")

    def error(self, *args):
        self.write(*args, level="error")


class WritersWrapper(IWriter):
    def __init__(self, writers, loglevel=None):
        super().__init__(loglevel or "debug")
        assert all(isinstance(w, IWriter) for w in writers)
        self.writers = writers

    def _write(self, *args, level):
        for writer in self.writers:
            writer.write(*args, level=level)


class TextWriter(IWriter):
    def __init__(self, writable, loglevel):
        super().__init__(loglevel)
        self.writable = writable

    def _write(self, *args, **kwargs):
        self.writable.write("".join(map(str, args)) + "\n")


class ColorTextWriter(IWriter):
    def __init__(self, writable, loglevel):
        super().__init__(loglevel)
        self.writable = writable

    def _write(self, *args, level):
        color = (
            {
                "debug": (0x4F, 0x8A, 0x10),
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

        args = [RichStr(x, defaults=dict(c=color, bg=bgcolor)) for x in args]
        self.writable.write(create_color_str(args) + "\n")


class LoggerWriter(IWriter):
    def __init__(self, logger):
        if not isinstance(logger, Logger):
            raise TypeError("logger must be logging.Logger")

        super().__init__("debug")
        self.logger = logger

    def _write(self, *args, level):
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
    def __init__(self, loglevel, fname):
        super().__init__(loglevel)

        os.makedirs(Path(fname).parent, exist_ok=True)

        self.fname = fname

    def _write(self, *args, **kwargs):
        with open(self.fname, "a") as f:
            f.write("".join(map(str, args)) + "\n")


HTML_BG_COLOR_MAP = {
    "debug": (0xDF, 0xF2, 0xBF),
    "info": (0xFF, 0xFF, 0xFF),
    "warning": (0xFE, 0xEF, 0xB3),
    "error": (0xFF, 0xD2, 0xD2),
}
HTML_COLOR_MAP = {
    "debug": (0x4F, 0x8A, 0x10),
    "info": (0, 0, 0),
    "warning": (0x9F, 0x60, 0x00),
    "error": (0xD8, 0x00, 0x0C),
}


class HTMLFileWriterOpenOnDemand(IWriter):
    def __init__(self, loglevel, fname, basedir=None):
        super().__init__(loglevel)

        os.makedirs(Path(fname).parent, exist_ok=True)

        self.basedir = basedir
        self.fname = fname

    def _write(self, *args, level):
        color = HTML_COLOR_MAP.get(level, "black")
        bgcolor = HTML_BG_COLOR_MAP.get(level, "white")

        args = [RichStr(x, defaults=dict(c=color)) for x in args]

        with open(self.fname, "a") as f:
            f.write(
                '<html><head><meta charset="utf-8"><title>log</title></head>'
                '<body><pre style="background-color: '
                f'rgb({bgcolor[0]}, {bgcolor[1]}, {bgcolor[2]})">'
            )
            f.write(create_html(args, self.basedir))
            f.write("</pre></body></html>")


class HTMLJupyterWriter(IWriter):
    def __init__(self, loglevel, basedir=None):
        super().__init__(loglevel)
        from IPython.display import display, HTML  # check if importable

        self.basedir = basedir

    def _write(self, *args, level):
        from IPython.display import display, HTML

        color = HTML_COLOR_MAP.get(level, "black")
        bgcolor = HTML_BG_COLOR_MAP.get(level, "white")

        args = [RichStr(x, defaults=dict(c=color)) for x in args]

        display(
            HTML(
                '<pre style="background-color: '
                f'rgb({bgcolor[0]}, {bgcolor[1]}, {bgcolor[2]})">'
                f"{create_html(args, self.basedir)}</pre>"
            )
        )


def create_html(sl, basedir=None):
    sl = [x if isinstance(x, RichStr) else RichStr(x) for x in sl]
    groups = []
    for s in sl:
        if len(groups) >= 1 and s.attr == groups[-1][0].attr:
            groups[-1].append(s)
        else:
            groups.append([s])

    outs = []
    for group in groups:
        s = RichStr("".join(group), **group[0].attr)
        outs.append(_richstr_to_html(s, basedir))

    return "".join(outs)


def _richstr_to_html(s, basedir):
    starts = []
    ends = []

    if s.link is not None:
        if basedir is not None:
            link = os.path.relpath(s.link, basedir)
        else:
            link = s.link
        starts.append(f'<a href="{Path(link).as_posix()}">')
        ends.append(f"</a>")

    styles = []
    if s.c is not None:
        styles.append(f"color: rgb({s.c[0]}, {s.c[1]}, {s.c[2]});")

    if s.bg is not None:
        styles.append(
            f"background-color: rgb({s.bg[0]}, {s.bg[1]}, {s.bg[2]});"
        )

    if len(styles) != 0:
        style = "".join(styles)
        starts.append(f'<span style="{style}">')
        ends.append(f"</span>")

    starts.append(html.escape(s))
    starts.extend(ends[::-1])
    return "".join(starts)


def create_color_str(sl):
    res = []
    last_c = None
    last_bg = None
    for s in sl:
        if not isinstance(s, RichStr):
            last_bg = None
            last_c = None
            res.append("\x1b[49m\x1b[39m" + s)
            continue

        if s.bg != last_bg:
            last_bg = s.bg
            if s.bg is None:
                res.append(f"\x1b[49m")
            else:
                res.append(f"\x1b[48;5;{_comp_8bit_term_color(*s.bg)}m")

        if s.c != last_c:
            last_c = s.c
            if s.c is None:
                res.append(f"\x1b[39m")
            else:
                res.append(f"\x1b[38;5;{_comp_8bit_term_color(*s.c)}m")

        res.append(str(s))

    res.append("\x1b[49m\x1b[39m")

    return "".join(res)


def _comp_8bit_term_color(r, g, b):
    r, g, b = (x * 6 // 256 for x in (r, g, b))
    return 16 + r * 36 + g * 6 + b


def term_is_jupyter():
    try:
        from IPython.core.getipython import get_ipython

        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except:
        return False
