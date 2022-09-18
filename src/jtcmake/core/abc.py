import abc
import enum


class IEvent:
    ...


class IRule(abc.ABC):
    @abc.abstractmethod
    def check_update(self, par_updated, dry_run):
        """
        Returns:
            check_update_result.IResult
        """
        ...

    @abc.abstractmethod
    def preprocess(self, callback):
        ...

    @abc.abstractmethod
    def postprocess(self, callback, succ):
        ...

    @property
    @abc.abstractmethod
    def method(self):
        ...

    @property
    @abc.abstractmethod
    def args(self):
        ...

    @property
    @abc.abstractmethod
    def kwargs(self):
        ...

    @property
    @abc.abstractmethod
    def deplist(self):
        ...
