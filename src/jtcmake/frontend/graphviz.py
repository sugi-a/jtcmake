import os, sys, re, json, subprocess
from html import escape

from ..logwriter.writer import term_is_jupyter
from .igroup import IGroup


def print_graphviz(group, output_file=None):
    if output_file is None:
        if term_is_jupyter():
            from IPython.display import display, SVG
            dot_code = gen_dot_code(group)
            svg = convert(dot_code, 'svg').decode()
            display(SVG(svg))
            return
        else:
            print(gen_dot_code(group))
            return
    else:
        dot_code = \
            gen_dot_code(group, os.path.dirname(output_file))

        if output_file[-4:] == '.svg':
            data = convert(dot_code, 'svg')
        else:
            raise ValueError(f'Output file\'s extension must be .svg')

        with open(output_file, 'wb') as f:
            f.write(data)


def gen_dot_code(group, basedir=None):
    if not isinstance(group, IGroup):
        raise TypeError('argument group must be Group')

    gid = {}
    rid = {}
    fid = {}

    res = []
    res.append('digraph {')
    res.append('  compound=true;')

    def rec_group(g, idt, par_prefix):
        gid[g] = len(gid)

        name = '<ROOT>' if len(g._name) == 0 else g._name[-1]

        if par_prefix == '':
            prefix = g._prefix
        elif g._prefix[:len(par_prefix)] == par_prefix:
            prefix = '... ' + g._prefix[len(par_prefix):]
        else:
            prefix = g._prefix

        res.append(idt + f'subgraph cluster{gid[g]} {{')
        res.append(
            idt +
            f'  label = <<B>{escape(name)}</B> '
            f'(<FONT FACE="monospace">{escape(prefix)}</FONT>)>;')
        res.append(idt + f'  style = "rounded";')

        for cname in g:
            c = g[cname]
            if isinstance(c, IGroup):
                rec_group(c, idt+'  ', g._prefix)
            else:
                proc_rulew(c, cname, idt + '  ', g._prefix)

        res.append(idt + '};');

    def proc_rulew(rw, name, idt, par_prefix):
        r = rw._rule
        rid[r] = len(rid)

        res.append(idt + f'subgraph cluster_r_{rid[r]} {{')
        res.append(idt + f'  label=<<B>{escape(name)}</B>>;')
        res.append(idt + f'  bgcolor = "#E0FFFF";')

        par_prefix = os.path.abspath(par_prefix + '_')[:-1]

        for yf in r.yfiles:
            fid[yf] = len(fid)

            p = str(yf.abspath)
            if par_prefix != '' and p[:len(par_prefix)] == par_prefix:
                p = '... ' + p[len(par_prefix):]
            else:
                p = str(yf.path)

            res.append(
                idt +
                f'  f{fid[yf]} ['
                f'label=<<FONT FACE="monospace">{escape(p)}</FONT>>; '
                f'style=filled; '
                f'color=white; '
                f'shape=plain; '
                f'margin="0.1,0.1"; '
                f'URL="{_mk_link(yf.path, basedir)}"; '
                f'];'
            )
        res.append(idt + f'}}')

    rec_group(group, '  ', '')

    for r, i in rid.items():
        for _k,xf in r.xfiles:
            if xf not in fid:
                fid[xf] = len(fid)
                res.append(
                    f'  f{fid[xf]} ['
                    f'label=<<FONT FACE="monospace">'
                    f'{escape(str(xf.path))}</FONT>>; '
                    f'shape=plain; '
                    f'URL="{_mk_link(xf.path, basedir)}"; '
                    f'];'
                )


            res.append(
                f'  f{fid[xf]} -> f{fid[r.yfiles[0]]} '
                f'[lhead=cluster_r_{rid[r]}];'
            )

    res.append('}')

    return '\n'.join(res) + '\n'


def convert(dot_code, t='svg'):
    p = subprocess.run(
        ['dot', f'-T{t}'],
        input=dot_code.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode())
        raise Exception(f'Error: dot exit with code {p.returncode}')

    return p.stdout


def save_to_file(dot_code, fname, t='svg'):
    with open(fname, 'wb') as f:
        f.write(convert(dot_code, t))


def _mk_link(p, basedir):
    basedir = basedir or os.getcwd()

    try:
        return os.path.relpath(p, basedir)
    except:
        pass

    return str(p)
