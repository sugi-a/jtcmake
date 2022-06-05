import sys, os
from .decls import NOP

def clean(rules, writer):
    for r in rules:
        clean_rule(r, writer)


def clean_rule(r, writer):
    if r.method is NOP:
        writer('Skip {r.name}: readonly\n', logkind='log')
        return

    if len(r.opaths) == 0:
        writer('Skip {r.name}: zero files\n', logkind='log')
        return

    writer(r.name + '\n')

    cleaned, failed, notfound = [], [], []

    for p in r.opaths:
        if os.path.exists(p):
            try:
                os.remove(p)
                cleaned.append(p)
            except:
                failed.append(p)
        else:
            notfound.append(p)

    if cleaned: writer(f'  Cleaned: {cleaned}\n')
    if notfound: writer(f'  Not found: {notfound}\n', logkind='log')
    if failed: writer(f'  Failed: {failed}\n', logkind='warning')

