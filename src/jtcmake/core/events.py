from traceback import TracebackException
from .abc import IEvent, IRule


class RuleEvent(IEvent):
    def __init__(self, rule: IRule):
        self._rule = rule

    @property
    def rule(self) -> IRule:
        return self._rule

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.rule})"


class ErrorRuleEvent(RuleEvent):
    def __init__(self, rule: IRule, err: BaseException):
        """
        Args:
            err (BaseException):
                This will be immediately coverted to a lighter format which
                does not have references to the stack frames.
                The format is currently traceback.TracebackException,
                which the implementor expect has no reference to stack frames.
                Fix this class if the implementor's expectation is not true.
        """
        super().__init__(rule)
        self.trace_exc = TracebackException.from_exception(err)


class Skip(RuleEvent):
    def __init__(self, rule: IRule, is_direct_target: bool):
        super().__init__(rule)
        self.is_direct_target = is_direct_target


class Start(RuleEvent):
    ...


class Done(RuleEvent):
    ...


class DryRun(RuleEvent):
    ...


class StopOnFail(IEvent):
    ...


class UpdateInfeasible(RuleEvent):
    def __init__(self, rule: IRule, reason: str):
        super().__init__(rule)
        self.reason = reason


class PreProcError(ErrorRuleEvent):
    ...


class ExecError(ErrorRuleEvent):
    ...


class PostProcError(ErrorRuleEvent):
    ...


class FatalError(ErrorRuleEvent):
    ...
