import abc

class Event:
    def __init__(self, msg=None):
        self.msg = msg


class IRule(abc.ABC):
    @abc.abstractmethod
    def should_update(self, updated_rules, dry_run): ...

    @abc.abstractmethod
    def preprocess(self, callback): ...

    @abc.abstractmethod
    def postprocess(self, callback, succ): ...

    @property
    @abc.abstractmethod
    def method(self): ...

    @property
    @abc.abstractmethod
    def args(self): ...

    @property
    @abc.abstractmethod
    def kwargs(self): ...

    @property
    @abc.abstractmethod
    def deplist(self): ...

