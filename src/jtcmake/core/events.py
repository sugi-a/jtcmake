from __future__ import annotations

from traceback import TracebackException
from typing import TypeVar

from .abc import IEvent, IRule

_T_Rule = TypeVar("_T_Rule", bound=IRule)


class RuleEvent(IEvent[_T_Rule]):
    def __init__(self, rule: _T_Rule):
        self._rule = rule

    @property
    def rule(self) -> _T_Rule:
        return self._rule

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.rule})"


class ErrorRuleEvent(RuleEvent[_T_Rule]):
    def __init__(self, rule: _T_Rule, err: BaseException):
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


class Skip(RuleEvent[_T_Rule]):
    def __init__(self, rule: _T_Rule, is_direct_target: bool):
        super().__init__(rule)
        self.is_direct_target = is_direct_target


class Start(RuleEvent[_T_Rule]):
    ...


class Done(RuleEvent[_T_Rule]):
    ...


class DryRun(RuleEvent[_T_Rule]):
    ...


class StopOnFail(IEvent[_T_Rule]):
    ...


class UpdateInfeasible(RuleEvent[_T_Rule]):
    def __init__(self, rule: _T_Rule, reason: str):
        super().__init__(rule)
        self.reason = reason


class PreProcError(ErrorRuleEvent[_T_Rule]):
    ...


class ExecError(ErrorRuleEvent[_T_Rule]):
    ...


class PostProcError(ErrorRuleEvent[_T_Rule]):
    ...


class FatalError(ErrorRuleEvent[_T_Rule]):
    ...
