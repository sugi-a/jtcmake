import sys, os
from ..core.rule import IRule
from ..logwriter.writer import term_is_jupyter, create_html
from .event_logger import tostrs_func_call


def print_method(rule):
    rule = rule._rule
    sl = []
    tostrs_func_call(sl, rule.method, rule.args, rule.kwargs)

    if term_is_jupyter():
        from IPython.display import display, HTML
        display(HTML('<pre>' + create_html(sl, os.getcwd()) + '</pre>'))
    else:
        sys.stdout.write(''.join(sl))
