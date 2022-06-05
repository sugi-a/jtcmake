from abc import ABCMeta, abstractmethod

NOP = object()


class Rule:
    def __init__(self, name, method, args, kwargs, depset, opaths, ipaths):
        self.name = name
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self.depset = depset
        self.opaths = opaths
        self.ipaths = ipaths

