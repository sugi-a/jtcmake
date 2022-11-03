from .core import IRule
from .group_mixins.basic import create_default_logwriter
from .event_logger import tostrs_func_call


def print_method(rule: IRule):
    info = rule._get_info()  # pyright: ignore [reportPrivateUsage]
    raw_rule = info.rule_store.rules[rule.raw_rule_id]
    sl = []
    tostrs_func_call(sl, raw_rule.method, raw_rule.args, raw_rule.kwargs)

    a = create_default_logwriter("debug")
    a.debug(*sl)
