import sys, os, html, re
from abc import ABCMeta, abstractmethod
from .simplehtmlbuilder import Element, to_html_str
from ..utils import isipynb

class Writer:
    def __init__(self, writable):
        self.writable = writable

    def __call__(self, text, link_map=None, logkind=None):
        self.writable.write(text)


class HTMLWriter:
    def __init__(self, writable):
        self.f = writable
        self.state = 0

    def __enter__(self):
        if self.state != 0:
            raise ValueError('Context may not be entered multiple times')
        self.state = 1

        self.f.write(
            '''
            <html>
                <head><meta charset="utf-8"><title>log</title></head>
                <body>
            '''
        )

        return self

    def __exit__(self, *args, **kwargs):
        if self.state == 1:
            self.state = 2
            self.f.write('</body></html>')

    def __call__(self, obj, link_map=None, logkind='info'):
        """logkind is log|info|warning|error|success"""
        if self.state != 1:
            raise ValueError('this must be used under with')

        self.f.write(to_html_str(create_msg_html(obj, link_map, logkind)))


class HTMLIpynbWriter:
    def __call__(self, obj, link_map=None, logkind='info'):
        from IPython.display import display, HTML
        obj = create_msg_html(obj, link_map, logkind)
        display(HTML(to_html_str(obj)))


def create_msg_html(obj, link_map=None, logkind='info'):
    if link_map is not None:
        obj = replace_link(obj, link_map)

    bgcolormap = {
        'success': '#DFF2BF',
        'log': 'white',
        'warning': '#FEEFB3',
        'error': '#FFD2D2',
    }
    colormap = {
        'success': '#4F8A10',
        'log': 'grey',
        'warning': '#9F6000',
        'error': '#D8000C',
    }
    color = colormap.get(logkind, 'black')
    bgcolor = bgcolormap.get(logkind, 'white')

    style = f'color: {color}; background-color: {bgcolor}'

    obj = Element('pre', Element('span', obj, style=style))

    return obj


def replace_link_of_str(s, link_map):
    if len(link_map) == 0:
        return s
    p = '|'.join(re.escape(l) for l in link_map.keys())
    p = rf'([\s\S]*?)({p})|([\s\S]+)'

    res = []
    for m in re.finditer(p, s):
        a,l,tail = m.groups()
        if tail is None:
            res.append(a)
            res.append(Element('a', l, href=link_map[l]))
        else:
            res.append(tail)
            
    return res

def replace_link(obj, link_map):
    if isinstance(obj, (tuple, list)):
        res = []
        return [replace_link(v, link_map) for v in obj]
    elif isinstance(obj, str):
        return replace_link_of_str(obj, link_map)
    elif isinstance(obj, Element):
        if obj.tag == 'a':
            return obj
        c = replace_link(obj.children, link_map)
        return Element(obj.tag, c, **obj.kwargs)


class TermWriter:
    def __init__(self, out):
        self.out = out

    def __call__(self, msg, link_map=None, logkind='info'):
        colormap = {
            'success': '36',
            'log': '37',
            'warning': '33',
            'error': '31',
        }
        color = colormap.get(logkind, '0')

        self.out.write(f'\x1b[{color}m{msg}\x1b[0m')
        

def get_default_writer():
    if isipynb():
        return HTMLIpynbWriter()
    else:
        if sys.stderr.isatty():
            return TermWriter(sys.stderr)
        else:
            return Writer(sys.stderr)

