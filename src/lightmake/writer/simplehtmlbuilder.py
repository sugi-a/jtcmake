import sys, os, html, re

_VOIDTAG = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

class Element:
    def __init__(self, tag, children, **kwargs):
        self.tag = tag.lower()
        self.kwargs = kwargs
        self.children = children

    def __str__(self):
        return to_html_str(self)


class EmptyElement(Element):
    def __init__(self, tag, **kwargs):
        super().__init__(tag, [], **kwargs)

    def __call__(self, *args):
        return Element(self.tag, args, **self.kwargs)
        


def to_html_str(obj):
    lst = []

    def rec(obj):
        if isinstance(obj, (tuple, list)):
            for c in obj:
                rec(c)
        elif isinstance(obj, str):
            lst.append(html.escape(obj))
        elif isinstance(obj, Element):
            kv2prop = lambda kv: f' {kv[0]}="{html.escape(str(kv[1]))}"'
            prop = ''.join(map(kv2prop, obj.kwargs.items()))

            if obj.tag in _VOIDTAG:
                lst.append(f'<{obj.tag}{prop}/>')
            else:
                lst.append(f'<{obj.tag}{prop}>')
                rec(obj.children)
                lst.append(f'</{obj.tag}>')
        elif obj is None:
            pass
        else:
            lst.append(html.escape(str(obj)))

    rec(obj)

    return ''.join(lst)
    
