import sys, os

from jtcmake.core.abc import IRule
from ..logwriter.writer import term_is_jupyter, create_html, create_color_str
from .event_logger import tostrs_func_call


def print_method(rule: IRule):
    rule = rule._rrule
    sl = []
    tostrs_func_call(sl, rule.method, rule.args, rule.kwargs)

    if term_is_jupyter():
        from IPython.display import display, HTML

        display(HTML("<pre>" + create_html(sl, os.getcwd()) + "</pre>"))
    elif sys.stderr.isatty():
        sys.stderr.write(create_color_str(sl))
    else:
        sys.stderr.write("".join(sl))
