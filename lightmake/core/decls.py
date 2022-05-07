from abc import ABCMeta, abstractmethod

NOP = object()

class ITarget(metaclass=ABCMeta):
    @abstractmethod
    def path(self):
        pass

    @abstractmethod
    def _get_rule(self):
        pass


class Rule:
    def __init__(self, name, method, args, kwargs, depset, self_path_set, dep_paths):
        self.name = name
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self.depset = depset
        self.self_path_set = self_path_set
        self.dep_path_set = dep_paths


